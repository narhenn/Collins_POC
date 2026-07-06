"""
bim_ifc.py — the BIM ingest pipeline: IFC → discipline-layer GLBs + metadata.

An IFC file carries the WHOLE building with semantics — walls, slabs, pipes,
ducts, cable trays, fixtures — with exact placement. This module splits it
into per-discipline layers that share one origin, so the viewer can overlay
them, fade the shell to X-ray, and let you see the systems through the walls:

    architecture   walls, windows, doors, roofs, stairs, coverings, furniture
    structure      beams, columns, slabs, footings, members
    plumbing       pipes, fittings, valves, pumps, tanks, sanitary terminals
    hvac           ducts, fittings, air terminals, fans, coils, boilers
    electrical     cable carriers/segments, outlets, switches, lights, boards
    fire_safety    sprinklers, alarms, sensors, extinguisher terminals
    site           terrain, external works, everything else

For each ingested building (one or MORE IFC files — e.g. ARCH + MEP models of
the same project) it writes, under  _models/bim/<bid>/ :

    <discipline>.glb    one GLB per discipline, world coordinates, node names
                        carry "<GlobalId>|<IfcClass>|<Name>" for click-inspect
    elements.json       per-element metadata (guid, class, name, storey,
                        discipline, center) — the inspect/fault-overlay index
    manifest.json       building summary the UI reads first

Processing runs on a background thread (big MEP models take minutes); poll
status() until state == "ready".
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger("orchestrator.bim")

BIM_DIR = Path(__file__).resolve().parent / "_models" / "bim"
BIM_DIR.mkdir(parents=True, exist_ok=True)

_REPO = Path(__file__).resolve().parents[2]

# Bundled sample buildings (committed under data/ifc-samples).
SAMPLES = {
    "duplex": {
        "name": "Duplex Apartment (Architecture + MEP)",
        "files": [_REPO / "data" / "ifc-samples" / "Duplex_A.ifc",
                  _REPO / "data" / "ifc-samples" / "Duplex_MEP.ifc"],
    },
}

# ── discipline classification ─────────────────────────────────────────

DISCIPLINES = {
    "architecture": {"label": "Architecture", "color": [0.82, 0.80, 0.76]},
    "structure":    {"label": "Structure", "color": [0.55, 0.57, 0.60]},
    "plumbing":     {"label": "Plumbing", "color": [0.13, 0.45, 0.85]},
    "hvac":         {"label": "HVAC", "color": [0.10, 0.65, 0.45]},
    "electrical":   {"label": "Electrical", "color": [0.95, 0.65, 0.10]},
    "fire_safety":  {"label": "Fire Safety", "color": [0.88, 0.15, 0.15]},
    "site":         {"label": "Site & Other", "color": [0.45, 0.55, 0.42]},
}

_CLASS_MAP = [
    # order matters — first match wins
    ("plumbing", ("IfcPipeSegment", "IfcPipeFitting", "IfcSanitaryTerminal",
                  "IfcValve", "IfcPump", "IfcTank", "IfcWasteTerminal",
                  "IfcInterceptor", "IfcStackTerminal")),
    ("hvac", ("IfcDuctSegment", "IfcDuctFitting", "IfcAirTerminal", "IfcDamper",
              "IfcFan", "IfcCoil", "IfcChiller", "IfcBoiler", "IfcAirToAirHeatRecovery",
              "IfcUnitaryEquipment", "IfcSpaceHeater", "IfcCooledBeam",
              "IfcCoolingTower", "IfcDuctSilencer", "IfcHumidifier")),
    ("electrical", ("IfcCableCarrierSegment", "IfcCableCarrierFitting",
                    "IfcCableSegment", "IfcCableFitting", "IfcOutlet",
                    "IfcSwitchingDevice", "IfcLightFixture", "IfcLamp",
                    "IfcElectricAppliance", "IfcElectricDistributionBoard",
                    "IfcElectricDistributionPoint", "IfcDistributionBoard",
                    "IfcTransformer", "IfcJunctionBox", "IfcElectricGenerator",
                    "IfcElectricMotor", "IfcAudioVisualAppliance",
                    "IfcCommunicationsAppliance", "IfcProtectiveDevice")),
    ("fire_safety", ("IfcFireSuppressionTerminal", "IfcAlarm", "IfcSensor",
                     "IfcDetector")),
    ("structure", ("IfcBeam", "IfcColumn", "IfcFooting", "IfcPile", "IfcMember",
                   "IfcReinforcingBar", "IfcReinforcingMesh", "IfcTendon",
                   "IfcSlab", "IfcRamp", "IfcRampFlight")),
    ("architecture", ("IfcWall", "IfcWallStandardCase", "IfcWindow", "IfcDoor",
                      "IfcRoof", "IfcStair", "IfcStairFlight", "IfcCovering",
                      "IfcCurtainWall", "IfcPlate", "IfcRailing",
                      "IfcFurnishingElement", "IfcFurniture", "IfcBuildingElementProxy")),
    ("site", ("IfcSite", "IfcGeographicElement", "IfcCivilElement")),
]

# generic flow classes → look at the containing system name for a better bucket
_FLOW_FALLBACK = ("IfcFlowSegment", "IfcFlowFitting", "IfcFlowTerminal",
                  "IfcFlowController", "IfcFlowMovingDevice",
                  "IfcFlowStorageDevice", "IfcEnergyConversionDevice",
                  "IfcDistributionElement", "IfcDistributionControlElement")


def classify(element) -> str:
    for disc, classes in _CLASS_MAP:
        for c in classes:
            if element.is_a(c):
                return disc
    for c in _FLOW_FALLBACK:
        if element.is_a(c):
            # try the distribution system / element name for a hint
            hint = " ".join(filter(None, [getattr(element, "Name", "") or "",
                                          getattr(element, "ObjectType", "") or ""])).lower()
            if any(k in hint for k in ("pipe", "sanit", "water", "waste", "plumb")):
                return "plumbing"
            if any(k in hint for k in ("duct", "air", "hvac", "vent", "mech")):
                return "hvac"
            if any(k in hint for k in ("cable", "elec", "light", "power", "conduit")):
                return "electrical"
            return "hvac"
    return "architecture"


# ── job registry (background processing) ──────────────────────────────

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def status(bid: str) -> dict:
    with _lock:
        job = _jobs.get(bid)
    if job:
        return dict(job)
    # already on disk from a previous run?
    man = BIM_DIR / bid / "manifest.json"
    if man.exists():
        return {"bid": bid, "state": "ready",
                "manifest": json.loads(man.read_text(encoding="utf-8"))}
    return {"bid": bid, "state": "unknown"}


def start(bid: str, paths: list[Path], name: str | None = None,
          force: bool = False) -> dict:
    """Kick off (or reuse) ingestion for a building id."""
    man = BIM_DIR / bid / "manifest.json"
    if man.exists() and not force:
        return status(bid)
    with _lock:
        if bid in _jobs and _jobs[bid]["state"] in ("queued", "processing"):
            return dict(_jobs[bid])
        _jobs[bid] = {"bid": bid, "state": "queued", "progress": 0,
                      "detail": "queued"}
    t = threading.Thread(target=_run, args=(bid, paths, name), daemon=True)
    t.start()
    return status(bid)


def _set(bid: str, **kw) -> None:
    with _lock:
        _jobs.setdefault(bid, {"bid": bid}).update(kw)


def _run(bid: str, paths: list[Path], name: str | None) -> None:
    t0 = time.time()
    try:
        _set(bid, state="processing", progress=5, detail="opening IFC")
        manifest = ingest(bid, paths, name=name,
                          on_progress=lambda p, d: _set(bid, progress=p, detail=d))
        _set(bid, state="ready", progress=100, manifest=manifest,
             detail=f"done in {time.time() - t0:.0f}s")
    except Exception as e:  # noqa: BLE001
        logger.exception("BIM ingest failed for %s", bid)
        _set(bid, state="error", detail=str(e))


# ── the ingest itself ─────────────────────────────────────────────────

def _geom_settings(ifcopenshell):
    import ifcopenshell.geom
    s = ifcopenshell.geom.settings()
    for k, v in (("use-world-coords", True), ("weld-vertices", True),
                 ("apply-default-materials", True)):
        try:
            s.set(k, v)
        except Exception:  # noqa: BLE001 — pre-0.8 constant-based API
            try:
                s.set(getattr(s, k.upper().replace("-", "_")), v)
            except Exception:
                pass
    return s


def _element_color(shape) -> list | None:
    try:
        mats = list(shape.geometry.materials)
        for m in mats:
            d = getattr(m, "diffuse", None)
            if d is None:
                continue
            try:
                rgb = [float(d.r()), float(d.g()), float(d.b())]
            except Exception:  # noqa: BLE001
                rgb = [float(x) for x in list(d)[:3]]
            if any(c > 0 for c in rgb):
                return rgb
    except Exception:  # noqa: BLE001
        pass
    return None


def ingest(bid: str, paths: list[Path], name: str | None = None,
           on_progress=None) -> dict:
    """Convert IFC file(s) into per-discipline GLBs + metadata. Blocking."""
    import multiprocessing

    import ifcopenshell
    import ifcopenshell.geom
    import numpy as np
    import trimesh
    from ifcopenshell.util import element as ifc_el

    def prog(p, d):
        if on_progress:
            on_progress(p, d)

    out = BIM_DIR / bid
    out.mkdir(parents=True, exist_ok=True)

    layers: dict[str, list] = {k: [] for k in DISCIPLINES}
    elements: list[dict] = []
    project_name = name
    storeys: set[str] = set()
    bounds_min = np.array([np.inf] * 3)
    bounds_max = np.array([-np.inf] * 3)

    for fi, path in enumerate(paths):
        prog(5 + fi * 5, f"opening {Path(path).name}")
        model = ifcopenshell.open(str(path))
        if project_name is None:
            try:
                project_name = model.by_type("IfcProject")[0].Name or bid
            except Exception:  # noqa: BLE001
                project_name = bid

        settings = _geom_settings(ifcopenshell)
        it = ifcopenshell.geom.iterator(settings, model,
                                        max(1, multiprocessing.cpu_count() - 1))
        if not it.initialize():
            logger.warning("no geometry in %s", path)
            continue
        n_products = max(1, len(model.by_type("IfcProduct")))
        done = 0
        while True:
            try:
                shape = it.get()
                el = model.by_guid(shape.guid)
                if not el.is_a("IfcSpace") and not el.is_a("IfcOpeningElement"):
                    g = shape.geometry
                    verts = np.array(g.verts, dtype=np.float64).reshape(-1, 3)
                    faces = np.array(g.faces, dtype=np.int64).reshape(-1, 3)
                    if len(verts) and len(faces):
                        disc = classify(el)
                        mesh = trimesh.Trimesh(vertices=verts, faces=faces,
                                               process=False)
                        rgb = _element_color(shape) or DISCIPLINES[disc]["color"]
                        rgba = [int(c * 255) for c in rgb] + [255]
                        mesh.visual = trimesh.visual.ColorVisuals(
                            mesh, face_colors=rgba)
                        ename = getattr(el, "Name", None) or el.is_a()
                        node = f"{shape.guid}|{el.is_a()}|{ename}"
                        layers[disc].append((node, mesh))
                        c = verts.mean(axis=0)
                        bounds_min = np.minimum(bounds_min, verts.min(axis=0))
                        bounds_max = np.maximum(bounds_max, verts.max(axis=0))
                        storey = None
                        try:
                            cont = ifc_el.get_container(el)
                            if cont is not None:
                                storey = cont.Name
                                storeys.add(storey)
                        except Exception:  # noqa: BLE001
                            pass
                        elements.append({
                            "guid": shape.guid, "class": el.is_a(),
                            "name": ename, "discipline": disc,
                            "storey": storey,
                            "center": [round(float(x), 3) for x in c],
                        })
            except Exception:  # noqa: BLE001 — a bad element never kills the run
                pass
            done += 1
            if done % 200 == 0:
                prog(min(90, 10 + int(80 * (fi + done / n_products) / len(paths))),
                     f"{Path(path).name}: {done} elements")
            if not it.next():
                break

    prog(92, "exporting layer GLBs")
    discs = []
    for disc, items in layers.items():
        if not items:
            continue
        scene = trimesh.Scene()
        for node, mesh in items:
            uniq = node
            i = 1
            while uniq in scene.geometry:
                uniq = f"{node}#{i}"
                i += 1
            scene.add_geometry(mesh, node_name=uniq, geom_name=uniq)
        glb_path = out / f"{disc}.glb"
        scene.export(str(glb_path))
        discs.append({"id": disc, "label": DISCIPLINES[disc]["label"],
                      "color": DISCIPLINES[disc]["color"],
                      "count": len(items), "glb": f"{disc}.glb",
                      "bytes": glb_path.stat().st_size})

    (out / "elements.json").write_text(json.dumps(elements), encoding="utf-8")
    manifest = {
        "bid": bid, "name": project_name or bid,
        "sources": [Path(p).name for p in paths],
        "disciplines": discs,
        "elements": len(elements),
        "storeys": sorted(storeys),
        "bounds": {"min": [round(float(x), 2) for x in bounds_min],
                   "max": [round(float(x), 2) for x in bounds_max]},
        "created": time.time(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1),
                                       encoding="utf-8")
    prog(100, "ready")
    return manifest


def building_dir(bid: str) -> Path:
    return BIM_DIR / bid


def list_buildings() -> list[dict]:
    out = []
    for man in BIM_DIR.glob("*/manifest.json"):
        try:
            m = json.loads(man.read_text(encoding="utf-8"))
            out.append({"bid": m["bid"], "name": m.get("name"),
                        "elements": m.get("elements"),
                        "disciplines": [d["id"] for d in m.get("disciplines", [])]})
        except Exception:  # noqa: BLE001
            pass
    return out
