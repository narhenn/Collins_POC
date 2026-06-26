"""
integration_routes.py — API endpoints for cross-platform integration.

These endpoints let the NextXR frontend trigger AUTOMIND workflow executions
and GoalCert training scenario runs. Each endpoint is best-effort: if the
target service is down, it returns a degraded response instead of failing.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.integration_clients import get_automind_client, get_goalcert_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integration", tags=["integration"])


# ---------------------------------------------------------------------------
#  AUTOMIND — trigger diagnosis workflow
# ---------------------------------------------------------------------------

class AutomindTriggerRequest(BaseModel):
    tenant_id: str
    incident_id: str
    finding_ids: list[str] = []
    affected_entity_id: str = ""
    diagnosis_text: str = ""


@router.post("/automind/diagnose")
def trigger_automind_diagnosis(req: AutomindTriggerRequest):
    """Trigger the Collins MRO Diagnosis workflow in AUTOMIND.
    Returns execution_id + SSE stream URL for real-time log display."""
    client = get_automind_client()
    if not client.available:
        return {
            "status": "unavailable",
            "message": "AUTOMIND agent not configured. Set AUTOMIND_AGENT_ID env var.",
        }
    result = client.trigger_diagnosis(
        tenant_id=req.tenant_id,
        incident_id=req.incident_id,
        finding_ids=req.finding_ids,
        affected_entity_id=req.affected_entity_id,
        diagnosis_text=req.diagnosis_text,
    )
    if result is None:
        return {
            "status": "degraded",
            "message": "AUTOMIND service unreachable. Diagnosis continues via NextXR engine.",
        }
    return {"status": "ok", **result}


@router.get("/automind/execution/{execution_id}")
def get_automind_execution(execution_id: str):
    """Fetch AUTOMIND execution results (after completion)."""
    client = get_automind_client()
    result = client.get_execution(execution_id)
    if result is None:
        raise HTTPException(502, "Could not fetch AUTOMIND execution")
    return result


# ---------------------------------------------------------------------------
#  GoalCert — generate training scenario from Action nodes
# ---------------------------------------------------------------------------

class GoalcertScenarioRequest(BaseModel):
    tenant_id: str
    fault_type: str = "chiller_cop_degradation"
    equipment_name: str = "Chiller-01"
    fault_description: str = ""
    remediation_steps: list[str] = []


@router.post("/goalcert/scenario")
def create_goalcert_scenario(req: GoalcertScenarioRequest):
    """Create an MRO training scenario in GoalCert from NextXR Action nodes.
    Uses the pre-built Collins chiller scenario as the base."""
    client = get_goalcert_client()

    # For the PoC, use the pre-seeded Collins chiller scenario
    scenario_id = "collins_chiller_mro"

    # Launch a run immediately
    run = client.launch_run(
        scenario_id=scenario_id,
        operator=f"Collins Technician ({req.tenant_id})",
        difficulty="Medium",
        duration_min=45,
    )
    if run is None:
        return {
            "status": "degraded",
            "message": "GoalCert service unreachable. Training scenario queued for later.",
            "scenario_id": scenario_id,
        }

    # Fetch the report
    report = client.get_report(run.get("id", ""))

    return {
        "status": "ok",
        "scenario_id": scenario_id,
        "run_id": run.get("id"),
        "run_status": run.get("status"),
        "scores": run.get("scores"),
        "kpis": run.get("kpis"),
        "summary": run.get("summary"),
        "objectives": run.get("objectives"),
        "duration_s": run.get("duration_s"),
        "report_available": report is not None,
    }


@router.get("/goalcert/run/{run_id}")
def get_goalcert_run(run_id: str):
    """Fetch a GoalCert run's full results."""
    client = get_goalcert_client()
    try:
        import urllib.request
        import json
        req = urllib.request.Request(
            f"{client.config.base_url}/api/runs/{run_id}",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        raise HTTPException(502, "Could not fetch GoalCert run")


@router.get("/goalcert/run/{run_id}/report")
def get_goalcert_report(run_id: str):
    """Fetch the After-Action Report from GoalCert."""
    client = get_goalcert_client()
    report = client.get_report(run_id)
    if report is None:
        raise HTTPException(502, "Could not fetch GoalCert report")
    return report


@router.get("/goalcert/run/{run_id}/events")
def get_goalcert_events(run_id: str):
    """Fetch the event timeline from a GoalCert run."""
    client = get_goalcert_client()
    events = client.get_events(run_id)
    if events is None:
        raise HTTPException(502, "Could not fetch GoalCert events")
    return events


# ---------------------------------------------------------------------------
#  Platform status — check what's available
# ---------------------------------------------------------------------------

@router.get("/status")
def integration_status():
    """Check which external platforms are reachable."""
    automind = get_automind_client()
    goalcert = get_goalcert_client()
    return {
        "automind": {
            "configured": automind.available,
            "url": automind.config.base_url,
        },
        "goalcert": {
            "configured": True,
            "available": goalcert.available,
            "url": goalcert.config.base_url,
        },
    }
