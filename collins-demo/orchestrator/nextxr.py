"""
nextxr.py — client for the NextXR Digital Twin core (the "mind").

We use NextXR as the authoritative twin store + live telemetry engine. The
orchestrator's Vision Agent (Claude) decides *what* the twin is; this module
materialises it in NextXR via the platform's own REST API and then reads live
data back out. No NextXR code is modified — only its public API is used.
"""
from __future__ import annotations

import logging
import httpx

from config import config
from claude_client import TwinSpec

logger = logging.getLogger("orchestrator.nextxr")

BASE = config.NEXTXR_URL.rstrip("/") + "/api/v1"


def _client() -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=30.0)


def health() -> dict:
    try:
        with _client() as c:
            r = c.get("/health")
            return {"ok": r.status_code == 200, **(r.json() if r.content else {})}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def build_twin(spec: TwinSpec) -> dict:
    """Create the aerospace-MRO twin in NextXR and locate the hero turbine asset.

    The aerospace-mro template seeds a SHACL-valid turbine MRO facility (rigs,
    test cells, sensors, power) — robust and zero-risk. We then resolve the
    turbine rig entity so the web app can bind hotspots and target the feed.
    """
    with _client() as c:
        # 1. Create + seed the twin (idempotent enough for a demo; each call
        #    makes a fresh tenant).
        r = c.post("/twins", json={
            "name": spec.machine_name or "Collins Turbine Engine",
            "domain": "turbine-engine",
        })
        r.raise_for_status()
        twin = r.json().get("twin", {})
        tenant = twin.get("tenant_id")
        seed_id = twin.get("seed_asset_id")

        # 2. The engine is the twin's seed asset; collect the rest for the 3D layer.
        machine = {"id": seed_id, "name": spec.machine_name}
        assets = []
        try:
            er = c.get("/entities", params={"tenant": tenant,
                                            "label": "PhysicalAsset", "limit": 100})
            nodes = (er.json() or {}).get("nodes", []) if er.status_code == 200 else []
            assets = [{"id": n.get("id"), "name": n.get("displayName"),
                       "type": (n.get("canonicalType") or "").split("#")[-1]}
                      for n in nodes]
            for n in nodes:
                if n.get("id") == seed_id:
                    machine = {"id": seed_id, "name": n.get("displayName")}
                    break
            if machine["id"] is None and nodes:
                machine = {"id": nodes[0].get("id"), "name": nodes[0].get("displayName")}
        except Exception as e:  # noqa: BLE001
            logger.warning("entity lookup failed: %s", e)

        return {"tenant": tenant, "twin": twin, "machine": machine, "assets": assets}


def list_templates() -> list[dict]:
    """The twin-domain templates the platform can seed (turbine, edm, facility…)."""
    try:
        with _client() as c:
            r = c.get("/twins/templates")
            return r.json().get("templates", []) if r.status_code == 200 else []
    except Exception as e:  # noqa: BLE001
        logger.warning("templates lookup failed: %s", e)
        return []


def build_domain(name: str, domain: str) -> dict:
    """Create a twin of any domain template; return tenant + primary machine +
    its physical assets. The primary machine is the seed asset (turbine engine,
    wire-EDM machine, UPS, chiller…) the live feed / 3D layer targets."""
    with _client() as c:
        r = c.post("/twins", json={"name": name or "Twin", "domain": domain})
        r.raise_for_status()
        twin = r.json().get("twin", {})
        tenant = twin.get("tenant_id")
        seed_id = twin.get("seed_asset_id")
        machine = {"id": seed_id, "name": name or "Twin"}
        assets = []
        try:
            er = c.get("/entities", params={"tenant": tenant,
                                            "label": "PhysicalAsset", "limit": 100})
            nodes = (er.json() or {}).get("nodes", []) if er.status_code == 200 else []
            assets = [{"id": n.get("id"), "name": n.get("displayName"),
                       "type": (n.get("canonicalType") or "").split("#")[-1]} for n in nodes]
            for n in nodes:
                if n.get("id") == seed_id:
                    machine = {"id": seed_id, "name": n.get("displayName")}
                    break
        except Exception as e:  # noqa: BLE001
            logger.warning("entity lookup failed: %s", e)
    return {"tenant": tenant, "twin": twin, "domain": domain,
            "machine": machine, "assets": assets}


def build_turbine(name: str) -> dict:
    """Create the turbine-engine twin with a given name; return tenant + machine + assets."""
    with _client() as c:
        r = c.post("/twins", json={"name": name or "Turbine Engine",
                                   "domain": "turbine-engine"})
        r.raise_for_status()
        twin = r.json().get("twin", {})
        tenant = twin.get("tenant_id")
        seed_id = twin.get("seed_asset_id")
        machine = {"id": seed_id, "name": name or "Turbine Engine"}
        assets = []
        try:
            er = c.get("/entities", params={"tenant": tenant,
                                            "label": "PhysicalAsset", "limit": 100})
            nodes = (er.json() or {}).get("nodes", []) if er.status_code == 200 else []
            assets = [{"id": n.get("id"), "name": n.get("displayName"),
                       "type": (n.get("canonicalType") or "").split("#")[-1]} for n in nodes]
            for n in nodes:
                if n.get("id") == seed_id:
                    machine = {"id": seed_id, "name": n.get("displayName")}
                    break
        except Exception as e:  # noqa: BLE001
            logger.warning("entity lookup failed: %s", e)
    return {"tenant": tenant, "twin": twin, "machine": machine, "assets": assets}


def start_feed(tenant: str, mode: str = "dynamics", speed: float = 60.0) -> dict:
    with _client() as c:
        r = c.post("/feed/start", params={"tenant": tenant, "mode": mode, "speed": speed})
        return r.json() if r.content else {"status": r.status_code}


def stop_feed() -> dict:
    with _client() as c:
        r = c.post("/feed/stop")
        return r.json() if r.content else {"status": r.status_code}


def project_sim(tenant: str, fault: str | None = None, severity: float = 0.85,
                control: float | None = None, horizon_min: float = 120.0,
                points: int = 120) -> dict:
    """Generic, domain-aware what-if projection: fork the live twin's current
    state, apply a hypothetical fault (+ control), project forward. Non-destructive."""
    with _client() as c:
        r = c.post(f"/ingest/{tenant}/project", json={
            "fault": fault, "severity": severity, "control": control,
            "horizon_min": horizon_min, "points": points})
        r.raise_for_status()
        return r.json()


def project(tenant: str, fault: str, severity: float = 0.85,
            throttle: float | None = 0.95, horizon_min: float = 30.0,
            step_s: float = 30.0) -> dict:
    """Run a what-if projection on the turbine twin's physics engine, forked from
    its present state (no writes to the live twin)."""
    with _client() as c:
        r = c.post("/scenario/project", json={
            "tenant": tenant, "fault": fault, "severity": severity,
            "throttle": throttle, "horizon_min": horizon_min, "step_s": step_s})
        r.raise_for_status()
        return r.json()


def simulate_step(tenant: str, throttle: float | None = None,
                  fault: str | None = None, severity: float = 0.6) -> dict:
    """Advance the LIVE real-time twin one physics step (3D-layer stand-in)."""
    with _client() as c:
        r = c.post("/ingest/simulate", json={
            "tenant": tenant, "throttle": throttle, "fault": fault,
            "severity": severity})
        return r.json() if r.content else {"status": r.status_code}


def ingest_state(tenant: str) -> dict:
    with _client() as c:
        r = c.get(f"/ingest/{tenant}/state")
        return r.json() if r.status_code == 200 else {"error": r.status_code}


def diagnostics(tenant: str) -> dict:
    """Detailed per-component / per-sensor snapshot of the live twin."""
    with _client() as c:
        r = c.get(f"/ingest/{tenant}/diagnostics")
        r.raise_for_status()
        return r.json()


def predict(tenant: str, horizon_min: float = 120.0, points: int = 120) -> dict:
    """Project the live twin's present trajectory forward (prediction engine)."""
    with _client() as c:
        r = c.get(f"/ingest/{tenant}/predict",
                  params={"horizon_min": horizon_min, "points": points})
        r.raise_for_status()
        return r.json()


def scenario_faults() -> list:
    with _client() as c:
        try:
            r = c.get("/scenario/faults")
            return r.json().get("faults", []) if r.status_code == 200 else []
        except Exception:  # noqa: BLE001
            return []


def _local(key: str) -> str:
    """Reduce a signal key to its local name, lowercased.
    'https://…/aero#exhaustGasTemp' or 'aero:exhaustGasTemp' -> 'exhaustgastemp'."""
    return key.split("#")[-1].split(":")[-1].lower()


def live(tenant: str) -> dict:
    """Aggregate the live picture: feed signals + findings + incidents.

    `signals` keeps the raw keys; `signals_by_local` is keyed by lowercased local
    name so the web app can bind a sensor (signal_key 'aero:exhaustGasTemp') to a
    feed signal ('…/aero#exhaustGasTemp') regardless of CURIE vs IRI form."""
    out: dict = {"signals": {}, "signals_by_local": {},
                 "findings": [], "incidents": [], "feed": {}}
    with _client() as c:
        try:
            f = c.get("/feed/status")
            if f.status_code == 200:
                fs = f.json()
                out["feed"] = {
                    "running": fs.get("running"),
                    "samples_processed": fs.get("samples_processed"),
                    "findings_emitted": fs.get("findings_emitted"),
                    "mode": fs.get("mode"),
                }
                out["signals"] = fs.get("signals", {})
                out["signals_by_local"] = {_local(k): v
                                           for k, v in out["signals"].items()}
        except Exception as e:  # noqa: BLE001
            logger.debug("feed status: %s", e)
        try:
            fr = c.get("/findings", params={"tenant": tenant, "limit": 25})
            if fr.status_code == 200:
                out["findings"] = fr.json() if isinstance(fr.json(), list) \
                    else fr.json().get("findings", [])
        except Exception as e:  # noqa: BLE001
            logger.debug("findings: %s", e)
        try:
            ir = c.get("/entities", params={"tenant": tenant,
                                            "label": "Incident", "limit": 10})
            if ir.status_code == 200:
                out["incidents"] = (ir.json() or {}).get("nodes", [])
        except Exception as e:  # noqa: BLE001
            logger.debug("incidents: %s", e)
    return out
