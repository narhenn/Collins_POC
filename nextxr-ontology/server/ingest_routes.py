"""
ingest_routes.py — sensor ingestion API for the turbine twin.

This is the integration seam for the 3D layer (the engine's stand-in). Three
ways to feed the twin:

  POST /api/v1/ingest/frame      push a full sensor frame (many readings)
  POST /api/v1/ingest/reading    push a single reading
  POST /api/v1/ingest/simulate   drive by throttle (+ optional injected fault);
                                  the backend physics produces the frame
  GET  /api/v1/ingest/{tenant}/state   latest frame + health + residuals + findings

Every path runs through the same behaviour -> findings -> diagnosis pipeline.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from turbine.ingest import get_service

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


def _parse_ts(ts: str | None) -> datetime:
    if not ts:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def _normalise(readings) -> dict[str, float]:
    """Accept {signal: value} or [{signal,value,unit}] -> {signal: value}."""
    if isinstance(readings, dict):
        return {k: float(v) for k, v in readings.items()}
    out: dict[str, float] = {}
    for r in readings or []:
        sig = r.get("signal")
        if sig is not None and r.get("value") is not None:
            out[sig] = float(r["value"])
    return out


class FrameRequest(BaseModel):
    tenant: str
    entity_id: str | None = None
    readings: dict | list = Field(default_factory=dict)
    ts: str | None = None


@router.post("/frame")
def ingest_frame(req: FrameRequest):
    twin = get_service().twin(req.tenant, req.entity_id)
    if twin is None:
        raise HTTPException(404, "No turbine entity for this tenant. Create a "
                                 "turbine twin first (domain 'turbine-engine').")
    readings = _normalise(req.readings)
    if not readings:
        raise HTTPException(400, "No readings provided.")
    result = twin.ingest(readings, _parse_ts(req.ts))
    return {"status": "ok", "entity_id": twin.entity_id, **result}


class ReadingRequest(BaseModel):
    tenant: str
    entity_id: str | None = None
    signal: str
    value: float
    unit: str | None = None
    ts: str | None = None


@router.post("/reading")
def ingest_reading(req: ReadingRequest):
    twin = get_service().twin(req.tenant, req.entity_id)
    if twin is None:
        raise HTTPException(404, "No turbine entity for this tenant.")
    result = twin.ingest({req.signal: req.value}, _parse_ts(req.ts))
    return {"status": "ok", "entity_id": twin.entity_id, **result}


class SimulateRequest(BaseModel):
    tenant: str
    entity_id: str | None = None
    throttle: float | None = None
    fault: str | None = None          # blade_erosion|nozzle_coking|bearing_wear|
                                      # oil_starvation|compressor_fouling|surge|none
    severity: float = 0.6
    dt: float = 1.0


@router.post("/simulate")
def ingest_simulate(req: SimulateRequest):
    twin = get_service().twin(req.tenant, req.entity_id)
    if twin is None:
        raise HTTPException(404, "No turbine entity for this tenant.")
    out = twin.simulate(throttle=req.throttle, fault=req.fault,
                        severity=req.severity, dt=req.dt)
    return {"status": "ok", "entity_id": twin.entity_id, **out}


@router.get("/{tenant}/state")
def ingest_state(tenant: str):
    twin = get_service().twin(tenant)
    if twin is None:
        raise HTTPException(404, "No turbine entity for this tenant.")
    return twin.state()


@router.get("/{tenant}/diagnostics")
def ingest_diagnostics(tenant: str):
    """Detailed per-component / per-sensor snapshot of the live twin."""
    twin = get_service().twin(tenant)
    if twin is None:
        raise HTTPException(404, "No turbine entity for this tenant.")
    return twin.diagnostics()


@router.get("/{tenant}/predict")
def ingest_predict(tenant: str, horizon_min: float = 120.0, points: int = 120):
    """Project the live twin's present trajectory forward (prediction engine)."""
    twin = get_service().twin(tenant)
    if twin is None:
        raise HTTPException(404, "No turbine entity for this tenant.")
    return twin.predict_forward(horizon_min=horizon_min, points=points)


class ProjectRequest(BaseModel):
    fault: str | None = None          # a domain fault id, or None/"none"
    severity: float = 0.85            # 0..1
    control: float | None = None      # throttle (turbine) / intensity (edm), 0..1
    horizon_min: float = 120.0
    points: int = 120


@router.post("/{tenant}/project")
def ingest_project(tenant: str, req: ProjectRequest):
    """Non-destructive what-if projection: fork the live twin's CURRENT state,
    apply a hypothetical fault (+ control), and project forward. The live twin is
    untouched. Used by the Scenario / Fault engine. Domain-aware (the twin class
    knows its own faults + physics)."""
    twin = get_service().twin(tenant)
    if twin is None:
        raise HTTPException(404, "No twin for this tenant.")
    if not hasattr(twin, "project"):
        raise HTTPException(400, "This twin does not support what-if projection.")
    return twin.project(fault=req.fault, severity=req.severity, control=req.control,
                        horizon_min=req.horizon_min, points=req.points)
