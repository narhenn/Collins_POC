"""Run endpoints: launch (compute+persist), list, detail, events, report."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import get_session
from app.db.models import Report, Run
from app.engine.config import RunConfig
from app.engine.environment import EnvironmentSpec
from app.services.runner import create_run

router = APIRouter(prefix="/api/runs", tags=["runs"])


class LaunchRequest(BaseModel):
    scenario_id: str
    environment_spec: EnvironmentSpec | None = None
    config: RunConfig | None = None
    operator: str | None = None


def _run_summary(run: Run) -> dict:
    return {
        "id": run.id, "scenario_id": run.scenario_id, "scenario_name": run.scenario_name,
        "operator": run.operator, "status": run.status, "duration_s": run.duration_s,
        "scores": run.scores, "kpis": run.kpis, "summary": run.summary,
        "created_at": run.created_at.isoformat(),
    }


@router.post("", status_code=201)
def launch_run(req: LaunchRequest, db: Session = Depends(get_session)) -> dict:
    try:
        run = create_run(
            db, scenario_id=req.scenario_id,
            environment_spec=req.environment_spec.model_dump() if req.environment_spec else None,
            config=req.config.model_dump() if req.config else None,
            operator=req.operator,
        )
    except KeyError:
        raise HTTPException(404, "scenario not found")
    detail = _run_summary(run)
    detail["environment"] = run.environment
    detail["objectives"] = run.objectives
    return detail


@router.get("")
def list_runs(limit: int = 20, db: Session = Depends(get_session)) -> list[dict]:
    rows = db.scalars(select(Run).order_by(Run.created_at.desc()).limit(limit)).all()
    return [_run_summary(r) for r in rows]


@router.get("/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_session)) -> dict:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    detail = _run_summary(run)
    detail["environment"] = run.environment
    detail["final_assets"] = run.final_assets
    detail["objectives"] = run.objectives
    detail["config"] = run.config
    return detail


@router.get("/{run_id}/events")
def get_run_events(run_id: str, db: Session = Depends(get_session)) -> list[dict]:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return run.events


@router.get("/{run_id}/report")
def get_run_report(run_id: str, db: Session = Depends(get_session)) -> dict:
    report = db.scalars(select(Report).where(Report.run_id == run_id)).first()
    if report is None:
        raise HTTPException(404, "report not found")
    return report.content
