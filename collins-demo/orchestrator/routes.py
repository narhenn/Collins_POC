"""
routes.py — the thin API the web app calls. Everything the UI needs is here;
the web app never talks to the platforms directly.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from fastapi import HTTPException
from fastapi.responses import FileResponse

import nextxr
import goalcert
import automind
import scenarios
import tripo
from claude_client import (
    vision_to_twin_spec, scenario_brief, author_scenario, analyze_outcome,
    diagnosis_agent, analysis_agent, build_twin_reply,
    narrate_sensors, generate_work_order, predictive_alert,
    cascade_analysis, troubleshoot_chat, parts_procurement_agent,
    generate_incident_report,
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
    image_b64: str | None = None      # required — image-to-3D only
    filename: str = "machine.png"


@router.post("/build-twin/generate")
def build_twin_generate(req: TwinGenerateRequest):
    """Build the live turbine twin now, and kick off the Tripo image->3D job.
    Returns immediately with the tenant + a Tripo task_id to poll."""
    built = nextxr.build_turbine(req.machine)
    tenant = built.get("tenant")
    # start the live twin streaming
    try:
        nextxr.simulate_step(tenant, throttle=0.9)
    except Exception:  # noqa: BLE001
        pass

    task_id, tripo_status = None, "disabled"
    if config.tripo_enabled and req.image_b64:
        tripo.log_balance("before generation")
        task_id, terr = tripo.start_image_task(tripo.b64_to_bytes(req.image_b64), req.filename)
        if task_id:
            tripo.register_job(task_id, tenant)
            tripo_status = "running"
        else:
            tripo_status = f"error: {terr or 'unknown'}"
    elif not config.tripo_enabled:
        tripo_status = "no_key"
    elif not req.image_b64:
        tripo_status = "no_image"

    return {"tenant": tenant, "machine": built.get("machine"),
            "assets": built.get("assets", []),
            "task_id": task_id, "tripo": tripo_status}


@router.get("/tripo/balance")
def tripo_balance():
    """Credits readout (also printed to the orchestrator terminal)."""
    return tripo.log_balance("on request")


@router.get("/build-twin/status/{task_id}")
def build_twin_status(task_id: str):
    return tripo.job_status(task_id)


@router.get("/model/{tenant}.glb")
def serve_model(tenant: str):
    p = tripo.model_path(tenant)
    if not p.exists():
        raise HTTPException(404, "model not generated yet")
    return FileResponse(p, media_type="model/gltf-binary")


@router.get("/health")
def health():
    """Reachability of all three platforms + whether Claude is wired."""
    return {
        "orchestrator": "ok",
        "claude": {"enabled": config.claude_enabled, "model": config.CLAUDE_MODEL},
        "tripo": {"enabled": config.tripo_enabled},
        "nextxr": nextxr.health(),
        "goalcert": goalcert.health(),
        "automind": automind.status(),
    }


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


# ── AI Co-Pilot: real-time narration, work orders, alerts, cascades ──

@router.get("/agents/narrate/{tenant}")
def narrate(tenant: str, machine: str = "Turbine Engine"):
    """Real-time AI narration — Claude watches the live sensor stream and
    issues a 1-2 sentence observation like an experienced test cell engineer.
    Includes prediction context so narration can reference upcoming limits."""
    state = nextxr.ingest_state(tenant)
    # Feed prediction into narration so it can say "redline in ~18 min"
    prediction = None
    try:
        prediction = nextxr.predict(tenant, horizon_min=60)
    except Exception:
        pass
    text = narrate_sensors(state, machine, prediction=prediction)
    return {"narration": text, "tenant": tenant}


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


# ── Multi-turn troubleshooting chatbot ────────────────────────────────

class TroubleshootRequest(BaseModel):
    tenant: str
    machine: str = "Turbine Engine"
    history: list[dict] = []
    message: str = ""


@router.post("/agents/troubleshoot")
def troubleshoot(req: TroubleshootRequest):
    """Multi-turn diagnostic chatbot — the AI Mechanic. Asks clarifying
    questions to narrow down the fault hypothesis."""
    diag = nextxr.diagnostics(req.tenant)
    reply = troubleshoot_chat(req.history, req.message, diag, req.machine)
    return reply.model_dump()


# ── Parts procurement agent ──────────────────────────────────────────

@router.post("/agents/procurement")
def procurement(req: WorkOrderRequest):
    """From the current diagnosis, generate a work order then identify
    specific parts needed with costs and lead times."""
    diag = nextxr.diagnostics(req.tenant)
    wo = generate_work_order(diag, req.machine)
    parts = parts_procurement_agent(wo.model_dump(), req.machine)
    return {"work_order": wo.model_dump(), "procurement": parts.model_dump()}


# ── Incident report generator ────────────────────────────────────────

@router.post("/agents/incident-report")
def incident_report(req: AgentRunRequest):
    """Generate a formal MRO incident report with regulatory closure."""
    diag = nextxr.diagnostics(req.tenant)
    findings = diag.get("findings", [])
    report = generate_incident_report(diag, findings, req.machine)
    return {"report": report.model_dump()}


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
