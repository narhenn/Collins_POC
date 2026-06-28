"""
scenario_routes.py — predictive what-if projection for the turbine twin.

POST /api/v1/scenario/project
    Fork the live twin's PRESENT state and project a scenario forward in a
    sandbox (no writes to the live twin). Returns trajectory + predicted events
    + outcome. The real-time twin keeps running untouched, so the simulation
    runs side by side with reality.

GET /api/v1/scenario/faults
    The fault catalogue the scenario builder can choose from.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from turbine.scenario import project, FAULTS
from turbine.ingest import get_service

router = APIRouter(prefix="/api/v1/scenario", tags=["scenario"])


@router.get("/faults")
def list_faults():
    return {"faults": [{"id": k, "description": v} for k, v in FAULTS.items()]}


class ProjectRequest(BaseModel):
    tenant: str | None = None       # fork from this twin's present state
    fault: str = "blade_erosion"
    severity: float = 0.7
    throttle: float | None = None   # None = keep the present throttle
    horizon_min: float = 30.0
    step_s: float = 30.0


@router.post("/project")
def project_scenario(req: ProjectRequest):
    # Seed from the live twin's present forward state when available.
    start_state = None
    if req.tenant:
        twin = get_service().twin(req.tenant)
        if twin is not None:
            start_state = twin.fwd_state   # deep-copied inside project()
    result = project({
        "fault": req.fault, "severity": req.severity, "throttle": req.throttle,
        "horizon_min": req.horizon_min, "step_s": req.step_s,
    }, start_state=start_state)
    result["tenant"] = req.tenant
    return result
