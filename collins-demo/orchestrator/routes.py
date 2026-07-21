"""
routes.py — the thin API the web app calls. Everything the UI needs is here;
the web app never talks to the platforms directly.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

import shutil

from fastapi import HTTPException
from fastapi.responses import FileResponse

import nextxr
import goalcert
import automind
import scenarios
import tripo
import runpod_3d
import bim_ifc
from claude_client import (
    vision_to_twin_spec, scenario_brief, author_scenario, analyze_outcome,
    diagnosis_agent, analysis_agent, build_twin_reply,
    narrate_sensors, generate_work_order, predictive_alert,
    cascade_analysis, asset_status, author_sim, analyze_projection,
    diagnose_snapshot, forecast_snapshot,
    troubleshoot_chat, parts_procurement_agent,
    generate_incident_report,
    build_procedure, scenario_chat, dashboard_chat,
)
from config import config

# Horizon presets the UI offers (label -> minutes).
HORIZONS = {
    "1 hour": 60, "2 hours": 120, "6 hours": 360, "12 hours": 720,
    "24 hours": 1440, "3 days": 4320, "1 week": 10080, "2 weeks": 20160,
    "1 month": 43200,
}

router = APIRouter(prefix="/api")


# ── Build a Twin: conversational agent + Tripo image->3D ─────────────

class TwinChatRequest(BaseModel):
    history: list[dict] = []
    message: str = ""


@router.post("/build-twin/message")
def build_twin_message(req: TwinChatRequest):
    r = build_twin_reply(req.history, req.message)
    return r.model_dump()


class TwinGenerateRequest(BaseModel):
    machine: str = "Turbine Engine"
    domain: str = "turbine-engine"     # which twin type to create
    image_b64: str | None = None       # required — image-to-3D only
    filename: str = "machine.png"
    quality: str = "fast"              # "fast" (256) or "high" (512)



@router.post("/build-twin/generate")
def build_twin_generate(req: TwinGenerateRequest):
    """Build a live twin of any domain, and kick off image->3D generation.
    Uses RunPod if configured, otherwise falls back to Tripo."""
    # Create a domain-aware twin (not just turbine)
    if req.domain == "turbine-engine":
        built = nextxr.build_turbine(req.machine)
    else:
        built = nextxr.build_domain(req.machine, req.domain)
    tenant = built.get("tenant")
    try:
        nextxr.simulate_step(tenant, throttle=0.9)
    except Exception:  # noqa: BLE001
        pass

    task_id = None
    provider = config.model_3d_provider  # "runpod", "tripo", or "none"
    gen_status = "disabled"

    if provider == "runpod" and req.image_b64:
        image_bytes = runpod_3d.b64_to_bytes(req.image_b64)
        task_id, err = runpod_3d.start_image_task(
            image_bytes, req.filename, quality=req.quality)
        if task_id:
            runpod_3d.register_job(task_id, tenant)
            gen_status = "running"
        else:
            gen_status = f"error: {err or 'unknown'}"
    elif provider == "tripo" and req.image_b64:
        tripo.log_balance("before generation")
        task_id, terr = tripo.start_image_task(tripo.b64_to_bytes(req.image_b64), req.filename)
        if task_id:
            tripo.register_job(task_id, tenant)
            gen_status = "running"
        else:
            gen_status = f"error: {terr or 'unknown'}"
    elif provider == "none":
        gen_status = "no_key"
    elif not req.image_b64:
        gen_status = "no_image"

    return {"tenant": tenant, "machine": built.get("machine"),
            "domain": req.domain, "assets": built.get("assets", []),
            "task_id": task_id, "tripo": gen_status,
            "provider": provider, "quality": req.quality}


# ── Stepped Build-a-Twin: (1) generate model → preview → (2) create twin ──
class ModelGenRequest(BaseModel):
    image_b64: str | None = None
    filename: str = "asset.png"
    quality: str = "fast"                 # draft|standard|ultra (fast/high = legacy aliases)
    extra_images_b64: list[str] = []      # more views of the SAME object (multi-image)


@router.post("/build-twin/model")
def build_twin_model(req: ModelGenRequest):
    """Generate ONLY the 3D model from the image (no twin yet). The GLB is stored
    under its task id so the UI can preview it and confirm before we wire a twin."""
    provider = config.model_3d_provider   # "runpod", "tripo", or "none"
    if provider == "none":
        return {"task_id": None, "status": "no_key", "provider": provider}
    if not req.image_b64:
        return {"task_id": None, "status": "no_image", "provider": provider}
    if provider == "runpod":
        extras = [runpod_3d.b64_to_bytes(b) for b in (req.extra_images_b64 or [])[:3]]
        task_id, err = runpod_3d.start_image_task(
            runpod_3d.b64_to_bytes(req.image_b64), req.filename,
            quality=req.quality, extra_images=extras)
        mod = runpod_3d
    else:  # tripo
        tripo.log_balance("before generation")
        task_id, err = tripo.start_image_task(tripo.b64_to_bytes(req.image_b64), req.filename)
        mod = tripo
    if not task_id:
        return {"task_id": None, "status": f"error: {err or 'unknown'}", "provider": provider}
    mod.register_job(task_id, task_id)     # keyed by task id (temp, pre-twin)
    return {"task_id": task_id, "status": "running", "provider": provider}


class TwinCreateRequest(BaseModel):
    machine: str = "New Twin"
    domain: str = "edm-machine"
    model_task_id: str | None = None       # attach a previewed model to the new twin


@router.post("/build-twin/create")
def build_twin_create(req: TwinCreateRequest):
    """Confirm step — build the live twin (physics + behaviours + sensors) and
    attach the already-generated 3D model to it."""
    if req.domain == "turbine-engine":
        built = nextxr.build_turbine(req.machine)
    else:
        built = nextxr.build_domain(req.machine, req.domain)
    tenant = built.get("tenant")
    try:
        nextxr.simulate_step(tenant, throttle=0.9)
    except Exception:  # noqa: BLE001
        pass
    model_url = None
    if req.model_task_id:
        src = runpod_3d.model_path(req.model_task_id)   # _models/<task_id>.glb (shared dir)
        if src.exists():
            try:
                shutil.copy(src, runpod_3d.model_path(tenant))
                model_url = f"/api/model/{tenant}.glb"
            except Exception:  # noqa: BLE001
                pass
    return {"tenant": tenant, "machine": built.get("machine"), "domain": req.domain,
            "assets": built.get("assets", []), "model_url": model_url}


class RunningRequest(BaseModel):
    running: bool = True


@router.post("/twin/{tenant}/running")
def set_twin_running(tenant: str, req: RunningRequest):
    """Start/stop the live twin — freezes or resumes its physics ticker."""
    ok = nextxr.set_running(tenant, req.running)
    return {"tenant": tenant, "running": req.running, "ok": ok}


@router.get("/tripo/balance")
def tripo_balance():
    """Credits readout (also printed to the orchestrator terminal)."""
    return tripo.log_balance("on request")


@router.get("/build-twin/status/{task_id}")
def build_twin_status(task_id: str):
    """Poll generation job status — checks both RunPod and Tripo registries."""
    rp = runpod_3d.job_status(task_id)
    if rp.get("status") != "unknown":
        return rp
    return tripo.job_status(task_id)


@router.get("/model/{tenant}.glb")
def serve_model(tenant: str):
    p = tripo.model_path(tenant)
    if not p.exists():
        raise HTTPException(404, "model not generated yet")
    return FileResponse(p, media_type="model/gltf-binary")


# ── BIM: IFC → discipline layers → X-ray viewer ──────────────────────

@router.get("/bim/buildings")
def bim_buildings():
    """Ingested buildings + available bundled samples."""
    return {"buildings": bim_ifc.list_buildings(),
            "samples": [{"id": k, "name": v["name"],
                         "available": all(Path(p).exists() for p in v["files"])}
                        for k, v in bim_ifc.SAMPLES.items()]}


@router.post("/bim/sample/{sample_id}")
def bim_ingest_sample(sample_id: str):
    """Ingest one of the bundled sample IFC sets (background; poll status)."""
    s = bim_ifc.SAMPLES.get(sample_id)
    if not s:
        raise HTTPException(404, f"unknown sample '{sample_id}'")
    return bim_ifc.start(sample_id, s["files"], name=s["name"])


@router.post("/bim/upload")
async def bim_upload(file: UploadFile = File(...)):
    """Upload an IFC file → background ingest into discipline layers."""
    if not (file.filename or "").lower().endswith(".ifc"):
        raise HTTPException(400, "expected an .ifc file")
    bid = re.sub(r"[^a-z0-9]+", "-", Path(file.filename).stem.lower()).strip("-") \
        or f"bldg-{int(time.time())}"
    dest = bim_ifc.building_dir(bid)
    dest.mkdir(parents=True, exist_ok=True)
    src = dest / "source.ifc"
    src.write_bytes(await file.read())
    return bim_ifc.start(bid, [src], name=Path(file.filename).stem, force=True)


@router.get("/bim/{bid}/status")
def bim_status(bid: str):
    return bim_ifc.status(bid)


@router.get("/bim/{bid}/file/{name}")
def bim_file(bid: str, name: str):
    """Serve a layer GLB / elements.json / manifest.json for a building."""
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "bad filename")
    p = bim_ifc.building_dir(bid) / name
    if not p.exists():
        raise HTTPException(404, f"{name} not found for '{bid}'")
    media = "model/gltf-binary" if name.endswith(".glb") else "application/json"
    return FileResponse(p, media_type=media)


@router.get("/health")
def health():
    """Reachability of all three platforms + whether Claude is wired. The platform
    probes run concurrently so a single down service (slow to refuse on Windows)
    can't stall the whole health check."""
    from concurrent.futures import ThreadPoolExecutor
    probes = {"nextxr": nextxr.health, "goalcert": goalcert.health,
              "automind": automind.status}
    out = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {k: ex.submit(fn) for k, fn in probes.items()}
        for k, f in futs.items():
            try:
                out[k] = f.result(timeout=6)
            except Exception as e:  # noqa: BLE001
                out[k] = {"ok": False, "error": str(e)}
    # Knowledge store stats
    try:
        from claude_client import knowledge_stats
        kb_stats = knowledge_stats()
    except Exception:  # noqa: BLE001
        kb_stats = {}
    return {
        "orchestrator": "ok",
        "claude": {"enabled": config.claude_enabled, "model": config.CLAUDE_MODEL},
        "tripo": {"enabled": config.tripo_enabled},
        "model_3d": {"provider": config.model_3d_provider,
                     "runpod": config.runpod_enabled, "tripo": config.tripo_enabled},
        "knowledge": kb_stats,
        **out,
    }


# ── Knowledge search API ──────────────────────────────────────────────

@router.get("/knowledge/search")
def knowledge_search(query: str, domain: str | None = None,
                     category: str | None = None, top_k: int = 5):
    """Semantic search over the agent knowledge base (fault library,
    compliance rules, past incidents)."""
    try:
        from knowledge import get_knowledge_store
        kb = get_knowledge_store()
        results = kb.search(query, domain=domain, category=category, top_k=top_k)
        return {"query": query, "results": results, "total": len(results)}
    except Exception as e:  # noqa: BLE001
        return {"query": query, "results": [], "error": str(e)}


@router.get("/agents/registry")
def get_agent_registry(domain: str = "edm-machine"):
    """Return agents available for a specific domain, grouped by category."""
    from agent_registry import agents_for_domain, agents_by_category, agent_count
    return {
        "domain": domain,
        "agents": agents_for_domain(domain),
        "by_category": agents_by_category(domain),
        "counts": agent_count(),
    }


@router.post("/knowledge/remember")
def knowledge_remember(domain: str, title: str, diagnosis: str, resolution: str):
    """Store a resolved incident in the knowledge base for future agent retrieval."""
    from claude_client import remember_resolution
    entry_id = remember_resolution(domain, title, diagnosis, resolution)
    return {"stored": bool(entry_id), "entry_id": entry_id}


# ── 1+2. Build the twin from an image + description ──────────────────

class BuildRequest(BaseModel):
    description: str = ""
    image_b64: str | None = None
    filename: str = "machine.png"
    start_feed: bool = True


@router.post("/build")
def build(req: BuildRequest):
    spec = vision_to_twin_spec(req.image_b64, req.description, req.filename)
    built = nextxr.build_twin(spec)
    tenant = built.get("tenant")
    if req.start_feed and tenant:
        try:
            nextxr.start_feed(tenant, mode="dynamics")
        except Exception:  # noqa: BLE001
            pass
    return {
        "tenant": tenant,
        "machine": built.get("machine"),
        "assets": built.get("assets", []),
        "spec": spec.model_dump(),
    }


# ── 4. Live monitoring ───────────────────────────────────────────────

@router.get("/twin/{tenant}/live")
def live(tenant: str):
    return nextxr.live(tenant)


@router.get("/twin/{tenant}/state")
def twin_state(tenant: str):
    """Turbine real-time twin state: latest signals, physics health, findings."""
    return nextxr.ingest_state(tenant)


class StepRequest(BaseModel):
    tenant: str
    throttle: float | None = None
    fault: str | None = None
    severity: float = 0.6


@router.post("/twin/step")
def twin_step(req: StepRequest):
    """Advance the LIVE real-time twin one physics step (the 3D layer's stand-in
    until it streams real sensor data). Separate from scenario projection."""
    return nextxr.simulate_step(req.tenant, req.throttle, req.fault, req.severity)


@router.get("/twin/{tenant}/diagnostics")
def twin_diagnostics(tenant: str):
    """Raw structured snapshot: every component + sensor with health/status."""
    return nextxr.diagnostics(tenant)


# ── Analysis + Diagnosis agents (run on command) ─────────────────────

@router.get("/agents/horizons")
def agent_horizons():
    return {"horizons": [{"label": k, "minutes": v} for k, v in HORIZONS.items()]}


class AgentRunRequest(BaseModel):
    tenant: str
    machine: str = "Turbine Engine"
    horizon_label: str = "2 hours"   # analysis only


@router.post("/agents/diagnosis")
def run_diagnosis(req: AgentRunRequest):
    """Diagnosis agent: detailed per-component / per-sensor report of the live twin."""
    diag = nextxr.diagnostics(req.tenant)
    report = diagnosis_agent(diag, req.machine)
    return {"diagnostics": diag, "report": report}


@router.post("/agents/analysis")
def run_analysis(req: AgentRunRequest):
    """Analysis agent + prediction engine: present state plus the projected
    assessment over the chosen horizon (1 hour … weeks)."""
    horizon_min = HORIZONS.get(req.horizon_label, 120)
    diag = nextxr.diagnostics(req.tenant)
    prediction = nextxr.predict(req.tenant, horizon_min=horizon_min)
    report = analysis_agent(diag, prediction, req.machine, req.horizon_label)
    return {"horizon_label": req.horizon_label, "horizon_min": horizon_min,
            "diagnostics": diag, "prediction": prediction, "report": report}


class FeedRequest(BaseModel):
    tenant: str
    mode: str = "dynamics"


@router.post("/twin/feed/start")
def feed_start(req: FeedRequest):
    return nextxr.start_feed(req.tenant, mode=req.mode)


@router.post("/twin/feed/stop")
def feed_stop():
    return nextxr.stop_feed()


# ── Twins library: list domain templates + create any twin ─────────

@router.get("/twins/templates")
def twins_templates():
    """The twin-domain templates the platform can seed (turbine, wire-EDM,
    facility, datacenter-style…) — what the Twins library offers."""
    return {"templates": nextxr.list_templates()}


class CreateTwinReq(BaseModel):
    name: str = "Twin"
    domain: str = "edm-machine"
    # fleet domain: optional network spec — an id ("melbourne-tram") or a full
    # custom network dict (nodes/routes/fleet…) so ANY fleet becomes a twin.
    network: dict | str | None = None


@router.post("/twins/create")
def twins_create(req: CreateTwinReq):
    """Create + seed a twin of any domain (e.g. 'edm-machine', 'turbine-engine',
    'tram-network'). Returns tenant + primary machine + assets; the live
    feed and every Claude agent then work against it unchanged."""
    options = None
    if req.domain == "tram-network" and req.network is not None:
        options = {"network": req.network}
    return nextxr.build_domain(req.name, req.domain, options=options)


@router.get("/twins/{tenant}/network")
def twin_network(tenant: str):
    """Live network map payload for fleet twins: geometry (nodes/routes/depots/
    substations), per-route status, and every vehicle's position."""
    return nextxr.network_state(tenant)


# Static fault catalogue per machine domain, so the Scenario panel can offer
# the right what-ifs. (Live faults are driven through the feed simulate path.)
TWIN_FAULTS = {
    "edm-machine": [
        {"id": "wire_break", "label": "Wire breakage"},
        {"id": "dielectric_contamination", "label": "Dielectric contamination"},
        {"id": "flushing_loss", "label": "Flushing loss"},
        {"id": "guide_wear", "label": "Guide / roller wear"},
        {"id": "chiller_failure", "label": "Dielectric chiller failure"},
        {"id": "servo_instability", "label": "Servo / gap-control instability"},
    ],
    "turbine-engine": [
        {"id": "blade_erosion", "label": "Blade erosion"},
        {"id": "nozzle_coking", "label": "Nozzle coking"},
        {"id": "bearing_wear", "label": "Bearing wear"},
        {"id": "oil_starvation", "label": "Oil starvation"},
        {"id": "compressor_fouling", "label": "Compressor fouling"},
        {"id": "surge", "label": "Compressor surge"},
    ],
    "datacenter": [
        {"id": "crac_failure", "label": "CRAC cooling failure"},
        {"id": "thermal_runaway", "label": "Rack thermal runaway"},
        {"id": "ups_depletion", "label": "UPS battery depletion"},
        {"id": "power_surge", "label": "Power distribution surge"},
    ],
    "hospital": [
        {"id": "laminar_loss", "label": "OR laminar-flow loss"},
        {"id": "medgas_drop", "label": "Medical gas pressure drop"},
        {"id": "coldchain_excursion", "label": "Pharmacy cold-chain excursion"},
        {"id": "hvac_fault", "label": "Ward HVAC fault"},
    ],
    "manufacturing": [
        {"id": "spindle_bearing", "label": "CNC spindle bearing wear"},
        {"id": "robot_overload", "label": "Robot joint overload"},
        {"id": "conveyor_jam", "label": "Conveyor jam / overload"},
        {"id": "compressor_fault", "label": "Compressed-air failure"},
    ],
    "tram-network": [
        {"id": "ohl_damage", "label": "Overhead line damage"},
        {"id": "substation_overload", "label": "Substation overload"},
        {"id": "track_buckling", "label": "Track buckling (heat)"},
        {"id": "switch_failure", "label": "Points / switch failure"},
        {"id": "signal_failure", "label": "Signalling failure"},
        {"id": "brake_degradation", "label": "Fleet brake degradation"},
        {"id": "pantograph_wear", "label": "Pantograph carbon wear"},
        {"id": "door_system_fault", "label": "Door system faults"},
        {"id": "wheel_flats", "label": "Wheel flats"},
        {"id": "demand_surge", "label": "Passenger demand surge"},
    ],
    "mrt-line": [
        {"id": "signal_failure", "label": "CBTC signal failure"},
        {"id": "door_malfunction", "label": "Train door malfunction"},
        {"id": "traction_undervoltage", "label": "Third rail undervoltage"},
        {"id": "tunnel_overheat", "label": "Tunnel HVAC failure"},
        {"id": "track_intrusion", "label": "Track intrusion detected"},
        {"id": "flooding", "label": "Station flooding"},
        {"id": "psd_desync", "label": "PSD-train door desync"},
        {"id": "escalator_fault", "label": "Escalator motor fault"},
    ],
    # Only the faults with full end-to-end support — real physics inject that
    # visibly drives the twin + a matching Repair-with-AI plan/cascade. (The thin
    # faults connector_stuck / insulation_fault / solar_hotcell / v2g_failure were
    # dropped from the dropdown so every option actually simulates.)
    "ev-network": [
        {"id": "thermal_runaway", "label": "Battery thermal runaway precursor"},
        {"id": "grid_overload", "label": "Grid transformer overload"},
        {"id": "charger_fault", "label": "EVSE communication fault"},
        {"id": "battery_degradation", "label": "Accelerated SoH decline"},
    ],
    "defence-base": [
        {"id": "perimeter_breach", "label": "Perimeter breach detected"},
        {"id": "radar_degradation", "label": "Radar TX power loss"},
        {"id": "ship_flooding", "label": "Ship compartment flooding"},
        {"id": "fuel_contamination", "label": "Fuel water contamination"},
        {"id": "uas_threat", "label": "Hostile UAS inbound"},
        {"id": "ammo_overheat", "label": "Ammunition storage overheat"},
        {"id": "comms_degradation", "label": "C4ISR link degradation"},
        {"id": "nbc_detection", "label": "NBC agent detected"},
    ],
}


@router.get("/twins/faults")
def twins_faults(domain: str = "edm-machine"):
    """The injectable fault catalogue for a twin domain (for the Scenario panel)."""
    return {"domain": domain, "faults": TWIN_FAULTS.get(domain, [])}


# External-situation presets per domain (the "Scenarios" tab examples). These are
# starting prompts; the agent authors a runnable spec from any free-text request.
SCENARIO_PRESETS = {
    "edm-machine": [
        {"title": "Summer heatwave", "description": "Shop ambient climbs toward 40C across a long shift and the dielectric chiller struggles to hold tank temperature."},
        {"title": "New dielectric batch", "description": "A supplier change delivered dielectric with higher conductivity and the de-ioniser resin is near end of life."},
        {"title": "Aggressive roughing run", "description": "Operator pushes maximum discharge energy for a fast roughing cut through thick stock."},
        {"title": "Unattended overnight cut", "description": "A long lights-out job runs for hours with nobody to clear debris or restore flushing."},
    ],
    "turbine-engine": [
        {"title": "Hot-and-high takeoff", "description": "Full-thrust ground run on a 45C day with reduced air density."},
        {"title": "Sustained max-continuous", "description": "Engine held at near-maximum thrust for an extended endurance run."},
        {"title": "Off-spec fuel batch", "description": "A batch of contaminated fuel feeds the combustor during a full-power run."},
    ],
    "datacenter": [
        {"title": "AI training surge", "description": "Every rack pushed to 100% load for hours during a large model training run."},
        {"title": "Cooling maintenance on a hot day", "description": "One CRAC unit is taken offline for service while ambient is high."},
        {"title": "Grid brownout", "description": "Utility power dips and the hall runs on UPS while the generator spins up."},
        {"title": "New high-density rack", "description": "A dense GPU rack is added, concentrating heat in one aisle."},
    ],
    "hospital": [
        {"title": "Flu-season surge", "description": "Wards and ED at full occupancy for an extended period, stressing HVAC and med-gas."},
        {"title": "Heatwave on the OR HVAC", "description": "A heatwave stresses the operating-theatre air handling and laminar flow."},
        {"title": "Power failure", "description": "Mains fails and the hospital runs on emergency generator power."},
        {"title": "Cold-chain delivery backlog", "description": "Pharmacy fridges are repeatedly opened during a large delivery."},
    ],
    "manufacturing": [
        {"title": "Three-shift rush order", "description": "Every line runs at maximum for three shifts to clear a rush order."},
        {"title": "Summer heat in the plant", "description": "High ambient temperature stresses motors, compressors and robotics."},
        {"title": "Skipped maintenance window", "description": "A planned lubrication/maintenance window is skipped under schedule pressure."},
        {"title": "Material hardness spike", "description": "A harder-than-spec material batch increases tool and spindle load."},
    ],
    "tram-network": [
        {"title": "40 °C heatwave afternoon", "description": "Extreme heat drives rail temperature toward the buckling limit while saloon HVAC load peaks the traction substations."},
        {"title": "Stadium event crowd surge", "description": "80,000 spectators leave the ground within 40 minutes — the event corridor loads spike and dwell times blow out."},
        {"title": "CBD signalling outage in the peak", "description": "An interlocking fault puts the core CBD junctions on manual working during the evening peak."},
        {"title": "Storm damage to the overhead", "description": "A storm brings a tree limb through the contact wire on one corridor; sections isolate and services divert."},
    ],
    "mrt-line": [
        {"title": "Peak-hour CBTC failure on NSL", "description": "Zone controller hardware fault causes communications loss for a 3-station section during evening rush. OCC must manage manual train movements."},
        {"title": "Flash flood entering Orchard station", "description": "70mm/hr rainfall overwhelms surface drainage. Water enters via escalator shaft to B2 level. Sump pumps at capacity."},
        {"title": "Tunnel fire smoke detection", "description": "Smoke detector alarm in tunnel between Bishan and Ang Mo Kio. Cause unknown — brake overheating vs actual fire. Ventilation direction critical."},
        {"title": "Mass event at Stadium MRT", "description": "NDP rehearsal ends — 45,000 spectators flood Stadium and Mountbatten stations simultaneously. Platform density approaching LOS E."},
    ],
    "ev-network": [
        {"title": "Battery thermal runaway at depot", "description": "Bus battery pack cell 47 temperature spiking. Off-gas H2 sensor triggered. Adjacent vehicles at risk if propagation begins."},
        {"title": "Grid overload during peak EV charging", "description": "30% EV penetration suburb. All residents plug in after work. Distribution transformer approaching 140°C hot-spot in 45 minutes."},
        {"title": "Charger fire at highway rest stop", "description": "350kW ultra-fast charger arcing fault. Cooling hose failure soaked power modules. OCPP connection lost. Adjacent vehicles at risk."},
        {"title": "V2G bidding during price spike", "description": "Wholesale electricity price spikes to 5x normal. 40 V2G-capable vehicles available for grid discharge. Optimise revenue vs battery health."},
    ],
    "defence-base": [
        {"title": "Coordinated base perimeter breach", "description": "Simultaneous sensor triggers at two sectors. 3 dismounted unknowns at Alpha, 1 vehicle at Bravo. Mortar impact on fuel point. SCADA anomaly on base utilities."},
        {"title": "Torpedo hit — ship damage control", "description": "Torpedo impact amidships. Flooding spaces 2-200-3-L through 2-200-3-R at 200 tonnes/minute. Fire in engine room. DCA must manage stability and DC."},
        {"title": "Drone swarm inbound — 24 UAVs", "description": "24 commercial quadrotors detected 3km out approaching from multiple vectors at 15 m/s. 4 minutes to perimeter. C-UAS engagement decision required."},
        {"title": "NBC agent release at vehicle gate", "description": "Chemical agent (VX) release at vehicle access point. 7 personnel potentially contaminated. Wind 5kt from 270°. MOPP level and decon site decisions needed."},
    ],
}


@router.get("/twins/scenarios")
def twins_scenarios(domain: str = "edm-machine"):
    """External-situation scenario presets for a twin domain (Scenarios tab)."""
    return {"domain": domain, "scenarios": SCENARIO_PRESETS.get(domain, [])}


def _twin_signals(tenant: str) -> list:
    try:
        st = nextxr.ingest_state(tenant)
        return list((st.get("latest") or {}).keys())
    except Exception:  # noqa: BLE001
        return []


class SimAuthorReq(BaseModel):
    tenant: str
    machine: str = "Machine"
    domain: str = "edm-machine"
    kind: str = "scenario"           # 'scenario' (external) | 'fault' (component)
    description: str = ""
    horizon_label: str = "2 hours"


@router.post("/agents/sim/author")
def sim_author(req: SimAuthorReq):
    """Agent: author a runnable what-if spec from a free-text situation/fault,
    grounded in THIS twin's fault catalogue + live signals."""
    faults = TWIN_FAULTS.get(req.domain, [])
    horizon_min = HORIZONS.get(req.horizon_label, 120)
    spec = author_sim(req.description, req.machine, req.domain, req.kind,
                      faults, _twin_signals(req.tenant), horizon_min)
    return {"spec": spec.model_dump()}


class SimRunReq(BaseModel):
    tenant: str
    machine: str = "Machine"
    domain: str = "edm-machine"
    fault: str | None = None
    severity: float = 0.85
    control: float | None = None
    horizon_min: float = 120.0
    title: str = ""
    analyze: bool = True


@router.post("/agents/sim/run")
def sim_run(req: SimRunReq):
    """Run a what-if spec: project it on the twin's physics (non-destructive) and
    add an AI outcome analysis."""
    projection = nextxr.project_sim(req.tenant, req.fault, req.severity,
                                    req.control, req.horizon_min)
    narrative = None
    if req.analyze:
        spec = {"title": req.title, "fault": req.fault, "severity": req.severity,
                "control": req.control, "horizon_min": req.horizon_min}
        narrative = analyze_projection(spec, projection, req.machine, req.domain)
    return {"projection": projection, "narrative": narrative}


# ── Interactive maintenance training + chat agents ──────────────────

class ProcedureReq(BaseModel):
    machine: str = "Machine"
    domain: str = ""
    fault: str = "none"
    title: str = ""
    context: str = ""


@router.post("/agents/procedure")
def agent_procedure(req: ProcedureReq):
    """A full ordered repair procedure (with per-step skip / wrong-order
    consequences) that drives the interactive maintenance trainer."""
    p = build_procedure(req.machine, req.domain, req.fault, req.title, req.context)
    return {"procedure": p.model_dump()}


class ChatReq(BaseModel):
    machine: str = "Machine"
    messages: list = []      # [{role: 'user'|'assistant', content: str}]
    context: dict = {}       # scenario/procedure/progress (scenario chat)
    snapshot: dict = {}      # live telemetry/findings (dashboard chat)


@router.post("/agents/scenario-chat")
def agent_scenario_chat(req: ChatReq):
    """Training coach chat — explains the outcome of any decision the trainee explores."""
    return {"reply": scenario_chat(req.messages, req.context, req.machine)}


@router.post("/agents/dashboard-chat")
def agent_dashboard_chat(req: ChatReq):
    """Live status chat — answers questions about the machine's current state."""
    return {"reply": dashboard_chat(req.messages, req.snapshot, req.machine)}


# ── AI Co-Pilot: real-time narration, work orders, alerts, cascades ──

@router.get("/agents/narrate/{tenant}")
def narrate(tenant: str, machine: str = "Turbine Engine"):
    """Real-time AI narration — Claude watches the live sensor stream and
    issues a 1-2 sentence observation like an experienced engineer."""
    state = nextxr.ingest_state(tenant)
    text = narrate_sensors(state, machine)
    return {"narration": text, "tenant": tenant}


class NarrateSnapshotReq(BaseModel):
    machine: str = "Machine"
    latest: dict = {}
    findings: list = []
    health: float | None = None


@router.post("/agents/narrate")
def narrate_snapshot(req: NarrateSnapshotReq):
    """Telemetry-snapshot narration — the AI co-pilot reasons from whatever live
    readings the caller provides, so every twin gets a real, telemetry-grounded
    observation (no backend tenant required)."""
    state = {"latest": req.latest, "findings": req.findings, "health": req.health}
    return {"narration": narrate_sensors(state, req.machine)}


class SnapshotReq(BaseModel):
    machine: str = "Machine"
    domain: str = ""
    latest: dict = {}
    findings: list = []
    components: list = []
    horizon_label: str = "6 hours"
    context: str = ""


@router.post("/agents/diagnose-snapshot")
def diagnose_snapshot_route(req: SnapshotReq):
    """Diagnosis on a telemetry snapshot (works for simulated twins too)."""
    return {"report": diagnose_snapshot(req.machine, req.domain, req.latest,
                                        req.findings, req.components)}


@router.post("/agents/forecast-snapshot")
def forecast_snapshot_route(req: SnapshotReq):
    """Qualitative forecast on a telemetry snapshot over a horizon."""
    return {"report": forecast_snapshot(req.machine, req.domain, req.latest,
                                        req.horizon_label, req.context)}


def _snapshot_diag(req: "SnapshotReq") -> dict:
    """Build a diagnostics-shaped dict from a snapshot so the work-order / cascade
    agents (which expect diagnostics) run on simulated twins."""
    sensors = [{"name": k.split(":")[-1], "signal": k, "value": v}
               for k, v in (req.latest or {}).items()]
    return {"machine": req.machine, "components": req.components or [],
            "sensors": sensors, "findings": req.findings or []}


@router.post("/agents/work-order-snapshot")
def work_order_snapshot(req: SnapshotReq):
    """AS9100-style work order from a snapshot (simulated twins included)."""
    wo = generate_work_order(_snapshot_diag(req), req.machine)
    return {"work_order": wo.model_dump()}


@router.post("/agents/cascade-snapshot")
def cascade_snapshot(req: SnapshotReq):
    """Cascade analysis from a snapshot."""
    return {"cascade_analysis": cascade_analysis(_snapshot_diag(req), {}, req.machine)}


class AssetStatusReq(BaseModel):
    machine: str = "Machine"
    domain: str = ""
    asset: dict = {}     # {id, name, type, status, metrics: {label: value}}


@router.post("/agents/asset")
def agent_asset_status(req: AssetStatusReq):
    """Detailed AI status for ONE component the operator clicked in the 3-D scene."""
    return {"status": asset_status(req.asset, req.machine, req.domain)}


class WorkOrderRequest(BaseModel):
    tenant: str
    machine: str = "Turbine Engine"


@router.post("/agents/work-order")
def work_order(req: WorkOrderRequest):
    """Generate an AS9100-compliant maintenance work order from the live twin's
    diagnosis. Printable, with ATA chapter refs, safety warnings, and parts list."""
    diag = nextxr.diagnostics(req.tenant)
    wo = generate_work_order(diag, req.machine)
    return {"work_order": wo.model_dump(), "diagnostics": diag}


@router.post("/agents/predict-alert")
def predict_alert(req: AgentRunRequest):
    """Run the prediction engine and generate a proactive alert if any operating
    limit is projected to be crossed within the forecast horizon."""
    horizon_min = HORIZONS.get(req.horizon_label, 120)
    prediction = nextxr.predict(req.tenant, horizon_min=horizon_min)
    alert = predictive_alert(prediction, req.machine)
    return {
        "alert": alert,
        "prediction_summary": {
            "horizon_min": horizon_min,
            "rul": prediction.get("rul", []),
            "severity": prediction.get("severity", "nominal"),
        },
    }


@router.post("/agents/cascade")
def cascade(req: AgentRunRequest):
    """Cross-system cascade reasoning — how degradation in one subsystem
    propagates to others."""
    horizon_min = HORIZONS.get(req.horizon_label, 120)
    diag = nextxr.diagnostics(req.tenant)
    prediction = nextxr.predict(req.tenant, horizon_min=horizon_min)
    analysis = cascade_analysis(diag, prediction, req.machine)
    return {"cascade_analysis": analysis, "diagnostics": diag}


# ── 5. AUTOMIND agents on top ────────────────────────────────────────

class DiagnoseRequest(BaseModel):
    tenant: str
    machine: str = ""


@router.post("/agents/diagnose")
def diagnose(req: DiagnoseRequest):
    snapshot = nextxr.live(req.tenant)
    context = {
        "machine": req.machine,
        "signals": snapshot.get("signals", {}),
        "findings": [
            {"label": f.get("displayName") or f.get("label"),
             "severity": f.get("severity"), "signal": f.get("signal")}
            for f in (snapshot.get("findings") or [])[:15]
        ],
        "incident_count": len(snapshot.get("incidents") or []),
    }
    return automind.diagnose(context)


# ── 6. GoalCert scenarios on top ─────────────────────────────────────

# ── Scenario builder: library, author (agent), run (projection) ──────

@router.get("/scenarios/library")
def scenarios_library():
    return {"scenarios": scenarios.library(),
            "faults": nextxr.scenario_faults() if hasattr(nextxr, "scenario_faults") else []}


class AuthorRequest(BaseModel):
    prompt: str
    machine: str = "Turbine Engine"
    sensors: list[str] = []


@router.post("/scenarios/author")
def scenarios_author(req: AuthorRequest):
    """Agent authors a runnable scenario from a natural-language request."""
    spec = author_scenario(req.prompt, req.machine, req.sensors)
    entry = scenarios.add_authored(spec)
    return {"scenario": entry, "spec": spec.model_dump()}


class RunRequest(BaseModel):
    tenant: str
    scenario_id: str | None = None      # pick a built/authored scenario
    # or specify ad-hoc:
    fault: str | None = None
    severity: float = 0.85
    throttle: float | None = 0.95
    horizon_min: float = 30.0
    machine: str = "Turbine Engine"
    analyze: bool = True


@router.post("/scenarios/run")
def scenarios_run(req: RunRequest):
    """Run a scenario projection on the twin's physics engine, forked from the
    present state, and (optionally) add an agent outcome analysis."""
    sc = scenarios.get(req.scenario_id) if req.scenario_id else None
    fault = (sc or {}).get("fault", req.fault or "blade_erosion")
    severity = (sc or {}).get("severity", req.severity)
    throttle = (sc or {}).get("throttle", req.throttle)
    horizon = (sc or {}).get("horizon_min", req.horizon_min)

    projection = nextxr.project(req.tenant, fault, severity, throttle, horizon)
    analysis = None
    if req.analyze:
        analysis = analyze_outcome(
            {"fault": fault, "severity": severity, "throttle": throttle,
             "horizon_min": horizon, "name": (sc or {}).get("name", fault)},
            projection, req.machine)
    return {
        "scenario": sc or {"fault": fault, "severity": severity,
                           "throttle": throttle, "horizon_min": horizon},
        "projection": projection,
        "analysis": analysis,
    }


# ── Multi-turn troubleshooting chatbot ────────────────────────────────

class TroubleshootRequest(BaseModel):
    tenant: str
    machine: str = "Turbine Engine"
    history: list[dict] = []
    message: str = ""


@router.post("/agents/troubleshoot")
def troubleshoot(req: TroubleshootRequest):
    """Multi-turn diagnostic chatbot — the AI Mechanic."""
    diag = nextxr.diagnostics(req.tenant) if req.tenant else {}
    reply = troubleshoot_chat(req.history, req.message, diag, req.machine)
    return reply.model_dump()


# ── Parts procurement agent ──────────────────────────────────────────

@router.post("/agents/procurement")
def procurement(req: AgentRunRequest):
    """From the current diagnosis, generate a work order then identify parts."""
    diag = nextxr.diagnostics(req.tenant) if req.tenant else {}
    wo = generate_work_order(diag, req.machine)
    parts = parts_procurement_agent(wo.model_dump(), req.machine)
    return {"work_order": wo.model_dump(), "procurement": parts.model_dump()}


# ── Incident report generator ────────────────────────────────────────

@router.post("/agents/incident-report")
def incident_report(req: AgentRunRequest):
    """Generate a formal MRO incident report with regulatory closure."""
    diag = nextxr.diagnostics(req.tenant) if req.tenant else {}
    findings = diag.get("findings", [])
    report = generate_incident_report(diag, findings, req.machine)
    return {"report": report.model_dump()}


# ── GoalCert training simulation ────────────────────────────────────

class GoalCertRunRequest(BaseModel):
    machine: str = "Machine"
    scenario_name: str = ""
    fault_summary: str = ""
    severity: str = "Medium"
    steps: list[str] = []

@router.post("/agents/goalcert/run")
def goalcert_run(req: GoalCertRunRequest):
    """Run a training scenario on the GoalCert simulation engine.
    Takes a scenario brief (from Claude authoring or manual input), creates
    the scenario on GoalCert, runs it, and returns the scored result."""
    from claude_client import ScenarioBrief
    brief = ScenarioBrief(
        name=req.scenario_name or "Maintenance Training",
        fault_summary=req.fault_summary or "Equipment fault requiring technician response",
        primary_signal="",
        severity=req.severity,
        steps=req.steps if req.steps else ["Diagnose the fault", "Apply corrective action", "Verify restoration"],
        expected_behavior="System returns to nominal operating parameters",
    )
    result = goalcert.create_and_run(brief, req.machine)
    return result
