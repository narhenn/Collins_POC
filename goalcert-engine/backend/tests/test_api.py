"""API + WebSocket integration tests (FastAPI TestClient over a temp SQLite DB)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_catalogs_populated(client):
    assert len(client.get("/api/catalog/assets").json()) >= 10
    assert len(client.get("/api/catalog/controls").json()) >= 8
    assert len(client.get("/api/catalog/techniques").json()) >= 15


def test_scenarios_seeded(client):
    scns = client.get("/api/scenarios").json()
    ids = {s["id"] for s in scns}
    assert "operation_black_phoenix" in ids
    topo = client.get("/api/scenarios/operation_black_phoenix/topology").json()
    assert len(topo["assets"]) == 14
    assert len(topo["controls"]) == 8


def test_launch_run_strong_vs_weak_and_report(client):
    # Strong posture (Easy, all controls on)
    strong = client.post("/api/runs", json={
        "scenario_id": "operation_black_phoenix",
        "config": {"difficulty": "Easy", "readiness": 95, "duration_min": 60},
    }).json()
    assert strong["status"] == "completed"
    assert strong["summary"]["ransomware"] is False

    # Weak posture (Expert, controls disabled)
    topo = client.get("/api/scenarios/operation_black_phoenix/topology").json()
    for c in topo["controls"]:
        c["enabled"] = False
    weak = client.post("/api/runs", json={
        "scenario_id": "operation_black_phoenix",
        "environment_spec": topo,
        "config": {"difficulty": "Expert", "readiness": 15, "duration_min": 60},
        "operator": "Tester",
    }).json()
    assert weak["summary"]["ransomware"] is True
    assert weak["scores"]["red"] > strong["scores"]["red"]

    # events + report
    events = client.get(f"/api/runs/{weak['id']}/events").json()
    assert len(events) > 20
    report = client.get(f"/api/runs/{weak['id']}/report").json()
    assert "exec_summary" in report
    assert report["scorecard"]["winner"] in ("Red", "Blue")
    assert len(report["timeline"]) > 5
    assert report["maturity_score"]["score"] <= 40  # weak posture => low maturity


def test_dashboard_and_leaderboard(client):
    dash = client.get("/api/dashboard").json()
    assert dash["total_runs"] >= 2
    assert "readiness" in dash
    lb = client.get("/api/leaderboard").json()
    assert isinstance(lb, list) and len(lb) >= 1


def test_websocket_stream_lifecycle(client):
    run = client.post("/api/runs", json={
        "scenario_id": "operation_black_phoenix",
        "config": {"difficulty": "Expert", "readiness": 40, "duration_min": 10},
    }).json()
    got_event = False
    completed = None
    with client.websocket_connect(f"/ws/runs/{run['id']}") as ws:
        init = ws.receive_json()
        assert init["type"] == "init"
        assert len(init["environment"]) == 14
        ws.send_json({"action": "speed", "value": 600})
        for _ in range(3000):
            msg = ws.receive_json()
            if msg["type"] == "event":
                got_event = True
            elif msg["type"] == "complete":
                completed = msg
                break
    assert got_event
    assert completed is not None and "scores" in completed
