"""
scenario.py — predictive what-if simulation for the turbine twin.

The real-time twin tells you what *is* happening. This projects what *would*
happen if a scenario (blade erosion, oil starvation, surge, sensor failure, ...)
unfolds from the present state — running the SAME turbine physics + behaviour
stack forward in a sandbox, with no writes to the live twin. It returns a
trajectory, a predicted event timeline (which fault fires and when), and an
outcome summary (time-to-redline, peak values, predicted incident, actions).

This is the engine the scenario builder drives: pick/author a scenario -> run it
side by side with the live twin -> see the outcome before it happens.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone, timedelta

from behaviors.registry import TelemetrySample
from turbine.physics import TurbinePhysics, TurbineState, SIGNALS, UNITS, redlines
from turbine.ingest import build_turbine_registry

ENT = "sandbox-engine"

# Friendly fault catalogue (also surfaced to the scenario-builder agent).
FAULTS = {
    "blade_erosion": "Turbine blade erosion — hot-section efficiency loss, EGT climbs.",
    "nozzle_coking": "Fuel-nozzle coking — uneven combustion, local hot streak.",
    "compressor_fouling": "Compressor fouling — reduced airflow, EGT creep.",
    "bearing_wear": "Bearing wear — rising vibration and N1 droop.",
    "oil_starvation": "Oil leak / starvation — oil temp up, oil pressure down.",
    "surge": "Compressor surge / stall — N1 collapse with EGT spike.",
    "sensor_failure": "EGT sensor failure — reading freezes while the engine "
                      "keeps degrading underneath (the twin flies blind).",
    "none": "Nominal — no fault injected (baseline projection).",
}

# Per-fault default remediation actions (used when the LLM analysis is off).
ACTIONS = {
    "blade_erosion": ["Reduce thrust", "Borescope the hot section",
                      "Schedule turbine module replacement"],
    "nozzle_coking": ["Inspect fuel nozzles", "Run fuel-system clean cycle"],
    "compressor_fouling": ["Perform compressor wash", "Inspect inlet filters"],
    "bearing_wear": ["Trend vibration", "Plan bearing replacement",
                     "Check oil debris monitor"],
    "oil_starvation": ["Check oil level and lines for leaks", "Inspect oil cooler",
                       "Shut down before bearing damage"],
    "surge": ["Reduce throttle", "Check variable geometry / bleed valves",
              "Inspect compressor for FOD"],
    "sensor_failure": ["Cross-check EGT against fuel/N1 model",
                       "Replace EGT thermocouple", "Do not trust the frozen reading"],
    "none": [],
}


class _SandboxQuery:
    """In-memory stand-in for GraphQuery so residual/surge behaviours can read
    the co-located frame without touching Neo4j."""

    def __init__(self):
        self._node: dict = {}

    def set_frame(self, frame: dict):
        # store local-named latest values (exhaustGasTemp, shaftSpeedN1, ...)
        self._node = {k.split("#")[-1].split(":")[-1]: v for k, v in frame.items()}

    def get_node(self, tenant_id, node_id):
        return dict(self._node)

    def get_property(self, tenant_id, node_id, key, default=None):
        return self._node.get(key, default)

    def list_by_label(self, tenant_id, label, limit=100):
        return []

    def get_findings(self, tenant_id, flagged_entity_id=None):
        return []


def project(scenario: dict, start_state: TurbineState | None = None,
            physics: TurbinePhysics | None = None) -> dict:
    """Run a what-if projection.

    scenario keys: fault, severity(0..1), throttle(0..1|None=keep present),
                   horizon_min, step_s.
    start_state: the present twin state to fork from (copied). Defaults healthy.
    """
    physics = physics or TurbinePhysics()
    state = copy.deepcopy(start_state) if start_state else physics.init_state()

    fault = scenario.get("fault", "none")
    severity = float(scenario.get("severity", 0.7))
    throttle = scenario.get("throttle")
    horizon_min = float(scenario.get("horizon_min", 30))
    step_s = float(scenario.get("step_s", 30))

    if throttle is not None:
        state.throttle = float(throttle)

    sensor_fault = fault == "sensor_failure"
    if sensor_fault:
        # The EGT sensor fails WHILE the hot section is actually degrading — so
        # the reported EGT freezes while the true EGT climbs. This is the danger
        # the twin's physics residual would otherwise catch: the operator flies
        # blind into an overheat.
        physics.inject(state, "blade_erosion", severity)
    elif fault != "none":
        physics.inject(state, fault, severity)

    q = _SandboxQuery()
    registry = build_turbine_registry()
    base = datetime.now(timezone.utc)

    steps = max(1, int(horizon_min * 60 / step_s))
    trajectory: list[dict] = []
    events: list[dict] = []
    fired: dict[str, dict] = {}
    frozen_egt = None
    time_to_redline = None
    peak = {"egt": 0.0, "vib": 0.0}
    trough = {"oil_press": 1e9, "health": 1.0}

    for i in range(steps + 1):
        t_min = round(i * step_s / 60.0, 2)
        true_frame = physics.forward(state, dt=step_s)

        # Sensor failure: the *reported* EGT freezes at the value when it failed,
        # even as the true engine keeps heating up. The behaviours see the frozen
        # value (so they don't fire) — the danger the twin's physics residual
        # would otherwise catch. We surface both true and reported.
        reported = dict(true_frame)
        if sensor_fault:
            if frozen_egt is None and t_min >= horizon_min * 0.2:
                frozen_egt = true_frame[SIGNALS["egt"]]
            if frozen_egt is not None:
                reported[SIGNALS["egt"]] = round(frozen_egt, 1)

        q.set_frame(reported)
        for sig, val in reported.items():
            sample = TelemetrySample(signal=sig, entity_id=ENT, value=float(val),
                                     unit=UNITS.get(sig, ""),
                                     timestamp=base + timedelta(seconds=i * step_s),
                                     tenant_id="sandbox")
            for f in registry.evaluate(sample, q):
                if f.behavior_id not in fired:
                    ev = {"t_min": t_min, "behavior_id": f.behavior_id,
                          "severity": f.severity, "message": f.message}
                    fired[f.behavior_id] = ev
                    events.append(ev)

        egt = true_frame[SIGNALS["egt"]]
        vib = true_frame[SIGNALS["vib"]]
        oil_p = true_frame[SIGNALS["oil_press"]]
        health = physics.health_index(true_frame)
        peak["egt"] = max(peak["egt"], egt)
        peak["vib"] = max(peak["vib"], vib)
        trough["oil_press"] = min(trough["oil_press"], oil_p)
        trough["health"] = min(trough["health"], health)
        if time_to_redline is None and egt >= redlines.egt:
            time_to_redline = t_min

        trajectory.append({
            "t_min": t_min,
            "egt": egt,
            "egt_reported": reported[SIGNALS["egt"]],
            "n1": true_frame[SIGNALS["n1"]],
            "vib": vib,
            "oil_temp": true_frame[SIGNALS["oil_temp"]],
            "oil_press": oil_p,
            "health": round(health, 3),
        })

    # Downsample trajectory to ~80 points for the UI.
    if len(trajectory) > 80:
        k = len(trajectory) // 80
        trajectory = trajectory[::k] + [trajectory[-1]]

    severities = [e["severity"] for e in events]
    outcome_severity = ("critical" if "critical" in severities
                        else "warning" if severities else "nominal")

    outcome = {
        "severity": outcome_severity,
        "predicted_incident": bool(events),
        "time_to_redline_min": time_to_redline,
        "peak_egt": round(peak["egt"], 1),
        "peak_vibration": round(peak["vib"], 3),
        "min_oil_pressure": round(trough["oil_press"], 1),
        "min_health": round(trough["health"], 3),
        "events_predicted": len(events),
        "recommended_actions": ACTIONS.get(fault, []),
        "blind_spot": sensor_fault,  # twin would not see the overheat
    }
    return {
        "scenario": {"fault": fault, "severity": severity, "throttle": state.throttle,
                     "horizon_min": horizon_min, "step_s": step_s,
                     "description": FAULTS.get(fault, fault)},
        "trajectory": trajectory,
        "events": events,
        "outcome": outcome,
    }
