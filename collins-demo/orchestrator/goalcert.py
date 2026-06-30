"""
goalcert.py — client for the GoalCert Simulation Engine.

Turns a Claude-authored scenario brief into a GoalCert scenario, runs it, and
returns the scored result. Uses GoalCert's public REST API only.
"""
from __future__ import annotations

import logging
import time
import httpx

from config import config

logger = logging.getLogger("orchestrator.goalcert")

BASE = config.GOALCERT_URL.rstrip("/") + "/api"


def _client() -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=60.0)


def health() -> dict:
    # Short timeout: the health badge must never stall the UI when GoalCert is down.
    try:
        with httpx.Client(base_url=BASE, timeout=2.5) as c:
            r = c.get("/health")
            return {"ok": r.status_code == 200, **(r.json() if r.content else {})}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def list_scenarios() -> list[dict]:
    try:
        with _client() as c:
            r = c.get("/scenarios")
            return r.json() if r.status_code == 200 else []
    except Exception as e:  # noqa: BLE001
        logger.warning("list_scenarios: %s", e)
        return []


def _slug(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:48] or "scenario"


def create_and_run(brief, machine: str, operator: str = "Collins Technician") -> dict:
    """Create a turbine scenario from the Claude brief, then run it.

    Builds a minimal-but-valid GoalCert Scenario (turbine asset topology +
    playbook from the brief's steps). If creation fails validation, falls back
    to launching the pre-seeded collins_chiller_mro scenario so the demo still
    produces a scored run.
    """
    scenario_id = _slug(brief.name)
    steps = [{"order": i + 1, "instruction": s}
             for i, s in enumerate(brief.steps or [])]
    scenario = {
        "id": scenario_id,
        "name": brief.name,
        "type": "ics",
        "industry": "aerospace_mro",
        "label": brief.severity,
        "description": brief.fault_summary,
        "recommended_topology": {
            "assets": [
                {"id": "turbine-01", "type": "ot_plc",
                 "name": machine or "Turbine Rig TR-01",
                 "role": "primary_asset", "zone": "ot", "criticality": 5},
                {"id": "test-controller", "type": "mes",
                 "name": "Test Cell Controller", "role": "it_ot_bridge",
                 "zone": "ot_dmz", "criticality": 3},
            ],
            "controls": [
                {"id": "c-siem", "type": "siem", "enabled": True},
                {"id": "c-seg", "type": "segmentation", "enabled": True},
            ],
        },
        "playbook": steps,
        "objectives": {"red": [s for s in (brief.steps or [])]},
    }

    with _client() as c:
        created = None
        try:
            r = c.post("/scenarios", json=scenario)
            if r.status_code in (200, 201):
                created = scenario_id
            elif r.status_code == 409:
                created = scenario_id  # already exists — reuse
            else:
                logger.warning("scenario create %s: %s", r.status_code, r.text[:300])
        except Exception as e:  # noqa: BLE001
            logger.warning("scenario create failed: %s", e)

        run_scenario_id = created or "collins_chiller_mro"
        try:
            rr = c.post("/runs", json={
                "scenario_id": run_scenario_id,
                "operator": operator,
                "config": {"difficulty": "Medium", "readiness": 70,
                           "duration_min": 30, "industry": "aerospace_mro"},
            })
            if rr.status_code not in (200, 201):
                return {"status": "degraded", "scenario_id": run_scenario_id,
                        "message": f"run failed ({rr.status_code})"}
            run = rr.json()
        except Exception as e:  # noqa: BLE001
            return {"status": "degraded", "scenario_id": run_scenario_id,
                    "message": f"GoalCert unreachable: {e}"}

        run_id = run.get("id")
        report = None
        if run_id:
            try:
                rep = c.get(f"/runs/{run_id}/report")
                report = rep.json() if rep.status_code == 200 else None
            except Exception:  # noqa: BLE001
                pass
        return {
            "status": "ok",
            "authored": created is not None,
            "scenario_id": run_scenario_id,
            "run_id": run_id,
            "scores": run.get("scores"),
            "kpis": run.get("kpis"),
            "summary": run.get("summary"),
            "objectives": run.get("objectives"),
            "duration_s": run.get("duration_s"),
            "report": report,
        }
