"""
predict.py — the prediction engine for the turbine twin.

Two jobs, both grounded in the same physics the live twin runs:

  1. component_health(state, frame) — derive a 0..1 health + status word for each
     engine component (compressor / combustor / turbine) and subsystem (rotor &
     bearings / lubrication) from the present physics state and sensor frame.

  2. predict(start_state, horizon) — project the twin's CURRENT trajectory forward
     (continuing whatever degradation/fault is active, else natural wear) and
     report: the trajectory, per-component health now vs. at the horizon, the
     predicted detection timeline, and remaining-useful-life / time-to-limit for
     each failure mode.

This is what the analysis agent reads to talk about the present AND the future.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone, timedelta

from behaviors.registry import TelemetrySample
from turbine.physics import TurbinePhysics, TurbineState, SIGNALS, UNITS, redlines
from turbine.ingest import build_turbine_registry


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _status(h: float) -> str:
    return ("good" if h >= 0.8 else "fair" if h >= 0.6
            else "degraded" if h >= 0.4 else "critical")


def component_health(state: TurbineState, frame: dict,
                     physics: TurbinePhysics) -> dict:
    """Per-component + per-subsystem health (0..1) with a status word."""
    d, lim = physics.d, physics.lim
    egt = frame.get(SIGNALS["egt"], d.egt)
    vib = frame.get(SIGNALS["vib"], d.vib)
    oilt = frame.get(SIGNALS["oil_temp"], d.oil_temp)
    oilp = frame.get(SIGNALS["oil_press"], d.oil_press)
    cond, wear, foul = state.condition, state.bearing_wear, state.oil_fouling

    egt_margin = _clamp(1 - max(0.0, egt - d.egt) / (lim.egt - d.egt))
    vib_margin = _clamp(1 - max(0.0, vib - d.vib) / (lim.vib - d.vib))
    oilt_margin = _clamp(1 - max(0.0, oilt - d.oil_temp) / (lim.oil_temp - d.oil_temp))
    oilp_margin = _clamp((oilp - lim.oil_press_min) / (d.oil_press - lim.oil_press_min))

    turbine = _clamp(0.55 * cond + 0.45 * egt_margin)
    combustor = _clamp(0.6 * egt_margin + 0.4 * cond)
    compressor = _clamp(1.0 - 0.45 * (1 - cond) - 0.30 * foul)
    bearings = _clamp(0.6 * (1 - wear) + 0.4 * vib_margin)
    lubrication = _clamp(min(1 - foul, oilt_margin, oilp_margin))
    overall = physics.health_index(frame)

    out = {}
    for name, h in (("compressor", compressor), ("combustor", combustor),
                    ("turbine", turbine), ("bearings", bearings),
                    ("lubrication", lubrication), ("overall", overall)):
        out[name] = {"health": round(h, 3), "status": _status(h)}
    return out


# Failure-mode limits we track time-to for RUL.
_LIMITS = [
    ("egt_redline", SIGNALS["egt"], "above", lambda: redlines.egt, "EGT redline"),
    ("oil_overtemp", SIGNALS["oil_temp"], "above", lambda: redlines.oil_temp, "oil over-temp"),
    ("oil_starvation", SIGNALS["oil_press"], "below", lambda: redlines.oil_press_min, "oil-pressure starvation"),
    ("vibration", SIGNALS["vib"], "above", lambda: redlines.vib, "vibration limit"),
]


def predict(start_state: TurbineState, horizon_min: float = 120.0,
            points: int = 120, physics: TurbinePhysics | None = None) -> dict:
    """Project the present trajectory forward `horizon_min` minutes.

    Continues the current fault/degradation (start_state carries it). Returns the
    trajectory (with per-component health), now/horizon component health, the
    predicted detection timeline, and time-to-limit (RUL) per failure mode.
    """
    physics = physics or TurbinePhysics()
    state = copy.deepcopy(start_state)

    horizon_s = horizon_min * 60.0
    step_s = max(1.0, horizon_s / points)
    steps = int(points)

    q_node: dict = {}

    class _Q:
        def get_node(self, t, n): return dict(q_node)
        def get_property(self, t, n, k, default=None): return q_node.get(k, default)
        def list_by_label(self, t, l, limit=100): return []
        def get_findings(self, t, e=None): return []

    q = _Q()
    registry = build_turbine_registry()
    base = datetime.now(timezone.utc)

    trajectory: list[dict] = []
    events: list[dict] = []
    fired: set[str] = set()
    ttl: dict[str, float | None] = {k[0]: None for k in _LIMITS}
    health_now = None

    for i in range(steps + 1):
        t_min = round(i * step_s / 60.0, 2)
        frame = physics.forward(state, dt=step_s)
        ch = component_health(state, frame, physics)
        if health_now is None:
            health_now = ch

        # detections
        q_node.clear()
        q_node.update({k.split("#")[-1].split(":")[-1]: v for k, v in frame.items()})
        for sig, val in frame.items():
            s = TelemetrySample(signal=sig, entity_id="predict", value=float(val),
                                unit=UNITS.get(sig, ""),
                                timestamp=base + timedelta(seconds=i * step_s),
                                tenant_id="predict")
            for f in registry.evaluate(s, q):
                if f.behavior_id not in fired:
                    fired.add(f.behavior_id)
                    events.append({"t_min": t_min, "behavior_id": f.behavior_id,
                                   "severity": f.severity, "message": f.message})

        # time-to-limit
        for key, sig, direction, lim_fn, _label in _LIMITS:
            if ttl[key] is None:
                v = frame.get(sig)
                lv = lim_fn()
                if v is not None and ((direction == "above" and v >= lv) or
                                      (direction == "below" and v <= lv)):
                    ttl[key] = t_min

        trajectory.append({
            "t_min": t_min,
            "egt": frame[SIGNALS["egt"]],
            "vib": frame[SIGNALS["vib"]],
            "oil_temp": frame[SIGNALS["oil_temp"]],
            "oil_press": frame[SIGNALS["oil_press"]],
            "health": ch["overall"]["health"],
            "turbine_h": ch["turbine"]["health"],
            "compressor_h": ch["compressor"]["health"],
            "bearings_h": ch["bearings"]["health"],
            "lubrication_h": ch["lubrication"]["health"],
        })

    if len(trajectory) > 100:
        k = len(trajectory) // 100
        trajectory = trajectory[::k] + [trajectory[-1]]

    health_horizon = component_health(state, physics.forward(copy.deepcopy(state), dt=0.0),
                                      physics)
    # use the last projected frame's component health for the horizon end
    health_horizon = {
        "compressor": {"health": trajectory[-1]["compressor_h"], "status": _status(trajectory[-1]["compressor_h"])},
        "turbine": {"health": trajectory[-1]["turbine_h"], "status": _status(trajectory[-1]["turbine_h"])},
        "bearings": {"health": trajectory[-1]["bearings_h"], "status": _status(trajectory[-1]["bearings_h"])},
        "lubrication": {"health": trajectory[-1]["lubrication_h"], "status": _status(trajectory[-1]["lubrication_h"])},
        "overall": {"health": trajectory[-1]["health"], "status": _status(trajectory[-1]["health"])},
    }

    rul = []
    label_map = {k[0]: k[4] for k in _LIMITS}
    for key, t in ttl.items():
        rul.append({"mode": label_map[key], "time_to_limit_min": t,
                    "within_horizon": t is not None})

    return {
        "horizon_min": horizon_min,
        "fault_active": start_state.fault if start_state.fault != "none" else None,
        "trajectory": trajectory,
        "events": events,
        "component_health_now": health_now,
        "component_health_horizon": health_horizon,
        "rul": rul,
        "severity": ("critical" if any(e["severity"] == "critical" for e in events)
                     else "warning" if events else "nominal"),
    }
