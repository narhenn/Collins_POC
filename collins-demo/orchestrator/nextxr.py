"""
nextxr.py — the orchestrator's twin client.

It used to HTTP-proxy every call to a separate NextXR backend (which needed
Neo4j + Docker). It now delegates to an IN-PROCESS physics engine (engine.py),
so the live Wire-EDM and turbine twins run inside the orchestrator with NO
database and NO Docker. The function names + return shapes are unchanged, so
routes.py and the agents keep working exactly as before.
"""
from __future__ import annotations

import logging

from config import config           # noqa: F401 — kept for compatibility
from claude_client import TwinSpec
from engine import get_engine

logger = logging.getLogger("orchestrator.nextxr")


def health() -> dict:
    try:
        get_engine()
        return {"ok": True, "mode": "in-process physics (no Docker / Neo4j)"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


# ── Twin creation ────────────────────────────────────────────────────
def _build(domain: str, name: str) -> dict:
    b = get_engine().build(domain, name)
    return {"tenant": b["tenant"], "domain": b["domain"],
            "twin": {"tenant_id": b["tenant"], "domain": b["domain"]},
            "machine": b["machine"], "assets": b["assets"]}


def build_twin(spec: TwinSpec) -> dict:
    """Build the turbine twin from a vision spec (the image→twin flow)."""
    return _build("turbine-engine", spec.machine_name or "Turbine Engine")


def build_turbine(name: str) -> dict:
    return _build("turbine-engine", name or "Turbine Engine")


def build_domain(name: str, domain: str) -> dict:
    return _build(domain, name)


def list_templates() -> list[dict]:
    return [
        {"key": "edm-machine", "label": "Wire EDM Machine"},
        {"key": "turbine-engine", "label": "Gas Turbine Engine"},
    ]


# ── Feed (the ticker runs automatically; these are no-ops kept for the API) ──
def start_feed(tenant: str, mode: str = "dynamics", speed: float = 60.0) -> dict:
    return {"status": "ok", "running": True, "mode": mode}


def stop_feed() -> dict:
    return {"status": "ok", "running": False}


# ── Live read surfaces ───────────────────────────────────────────────
def ingest_state(tenant: str) -> dict:
    tw = get_engine().twin(tenant)
    if not tw:
        return {"domain": None, "health": None, "latest": {}, "findings": [], "incidents": []}
    return tw.state_dict()


def live(tenant: str) -> dict:
    tw = get_engine().twin(tenant)
    if not tw:
        return {"signals": {}, "findings": [], "incidents": [], "feed": {"running": False}}
    st = tw.state_dict()
    return {"signals": st["latest"], "findings": st["findings"],
            "incidents": st["incidents"], "feed": {"running": True}}


def diagnostics(tenant: str) -> dict:
    tw = get_engine().twin(tenant)
    if not tw:
        return {"machine": {"name": tenant}, "components": [], "sensors": [],
                "findings": [], "overall_health": None, "latest": {}}
    return tw.diagnostics()


def predict(tenant: str, horizon_min: float = 120.0, points: int = 120) -> dict:
    tw = get_engine().twin(tenant)
    if not tw:
        return {"trajectory": [], "rul": [], "events": [], "severity": "nominal"}
    return tw.predict_forward(horizon_min=horizon_min, points=points)


def project_sim(tenant: str, fault=None, severity: float = 0.85, control=None,
                horizon_min: float = 120.0, points: int = 120) -> dict:
    tw = get_engine().twin(tenant)
    if not tw:
        return {"trajectory": [], "rul": [], "events": [], "severity": "nominal"}
    return tw.project(fault=fault, severity=severity, control=control,
                      horizon_min=horizon_min, points=points)


def project(tenant: str, fault: str, severity: float = 0.85, throttle=None,
            horizon_min: float = 30.0, step_s: float = 30.0) -> dict:
    """Legacy turbine what-if — mapped onto the generic projection."""
    return project_sim(tenant, fault=fault, severity=severity, control=throttle,
                       horizon_min=horizon_min)


def set_running(tenant: str, running: bool) -> bool:
    """Start/stop a live twin — the engine ticker only advances twins with
    live=True, so this truly freezes/resumes the simulation."""
    tw = get_engine().twin(tenant)
    if not tw:
        return False
    tw.live = bool(running)
    return True


def simulate_step(tenant: str, throttle=None, fault=None, severity: float = 0.6) -> dict:
    tw = get_engine().twin(tenant)
    if not tw:
        return {"status": "no-twin"}
    frame = tw.simulate(throttle=throttle, fault=fault, severity=severity, dt=2.0)
    return {"status": "ok", "frame": frame}


def scenario_faults() -> list:
    return []
