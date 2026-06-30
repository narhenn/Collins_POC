"""
predict.py — the prediction engine for the wire-EDM twin.

Two jobs, both grounded in the same physics the live twin runs:

  1. component_health(state, frame) — derive a 0..1 health + status word for each
     subsystem (generator / dielectric / wire system / guides & axes) from the
     present physics state and telemetry frame.

  2. predict(start_state, horizon) — project the twin's CURRENT trajectory
     forward (continuing whatever degradation/fault is active, else natural
     wear) and report: the trajectory, per-subsystem health now vs. at the
     horizon, the predicted detection timeline, and time-to-limit / RUL for each
     failure mode.

This is what the analysis agent reads to talk about the present AND the future.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone, timedelta

from behaviors.registry import TelemetrySample
from behaviors.edm import build_edm_registry
from edm.physics import EDMPhysics, EDMState, SIGNALS, UNITS, redlines


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _status(h: float) -> str:
    return ("good" if h >= 0.8 else "fair" if h >= 0.6
            else "degraded" if h >= 0.4 else "critical")


def component_health(state: EDMState, frame: dict,
                     physics: EDMPhysics) -> dict:
    """Per-subsystem health (0..1) with a status word."""
    d, lim = physics.d, physics.lim
    gap_v = frame.get(SIGNALS["gap_v"], d.gap_v)
    short = frame.get(SIGNALS["short_rate"], d.base_short * 100.0)   # %
    cond = frame.get(SIGNALS["die_cond"], d.die_cond)
    temp = frame.get(SIGNALS["die_temp"], d.die_temp)
    flow = frame.get(SIGNALS["die_flow"], d.die_flow)
    press = frame.get(SIGNALS["die_press"], d.die_press)
    tension = frame.get(SIGNALS["wire_tension"], d.wire_tension)
    break_r = frame.get(SIGNALS["break_risk"], 0.0)                  # %
    wear = frame.get(SIGNALS["wire_wear"], 0.0) / 100.0
    ra = frame.get(SIGNALS["ra"], d.ra)

    gap_margin = _clamp((gap_v - lim.gap_v_min) / (d.gap_v - lim.gap_v_min))
    short_margin = _clamp(1 - short / lim.short_rate)
    cond_margin = _clamp(1 - max(0.0, cond - d.die_cond) / (lim.die_cond - d.die_cond))
    temp_margin = _clamp(1 - max(0.0, temp - d.die_temp) / (lim.die_temp - d.die_temp))
    flush = physics.flush_efficiency(flow, press)
    tension_margin = _clamp((tension - lim.wire_tension_min) /
                            (d.wire_tension - lim.wire_tension_min))
    break_margin = _clamp(1 - break_r / lim.break_risk)
    ra_margin = _clamp(1 - max(0.0, ra - d.ra) / (3.0 - d.ra))

    generator = _clamp(0.6 * short_margin + 0.4 * gap_margin)
    dielectric = _clamp(min(cond_margin, temp_margin, flush))
    wire_system = _clamp(0.5 * break_margin + 0.3 * tension_margin + 0.2 * (1 - wear))
    guides_axes = _clamp(0.7 * (1 - state.guide_wear) + 0.3 * ra_margin)
    overall = physics.health_index(frame)

    out = {}
    for name, h in (("generator", generator), ("dielectric", dielectric),
                    ("wire_system", wire_system), ("guides_axes", guides_axes),
                    ("overall", overall)):
        out[name] = {"health": round(h, 3), "status": _status(h)}
    return out


# Failure-mode limits we track time-to for RUL. (direction relative to limit.)
_LIMITS = [
    ("die_overtemp", SIGNALS["die_temp"], "above", lambda: redlines.die_temp,
     "dielectric over-temperature"),
    ("dielectric_unstable", SIGNALS["die_cond"], "above", lambda: redlines.die_cond,
     "dielectric conductivity limit"),
    ("short_circuit", SIGNALS["short_rate"], "above", lambda: redlines.short_rate,
     "short-circuit rate limit"),
    ("wire_break", SIGNALS["break_risk"], "above", lambda: redlines.break_risk,
     "wire-break risk limit"),
    ("flushing_loss", SIGNALS["die_press"], "below", lambda: redlines.die_press_min,
     "flushing-pressure loss"),
]


def predict(start_state: EDMState, horizon_min: float = 120.0,
            points: int = 120, physics: EDMPhysics | None = None) -> dict:
    """Project the present trajectory forward `horizon_min` minutes.

    Continues the current fault/degradation (start_state carries it). Returns the
    trajectory (with per-subsystem health), now/horizon health, the predicted
    detection timeline, and time-to-limit (RUL) per failure mode.
    """
    physics = physics or EDMPhysics()
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
    registry = build_edm_registry()
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
            "cut_speed": frame[SIGNALS["cut_speed"]],
            "short_rate": frame[SIGNALS["short_rate"]],
            "die_temp": frame[SIGNALS["die_temp"]],
            "die_cond": frame[SIGNALS["die_cond"]],
            "break_risk": frame[SIGNALS["break_risk"]],
            "health": ch["overall"]["health"],
            "generator_h": ch["generator"]["health"],
            "dielectric_h": ch["dielectric"]["health"],
            "wire_system_h": ch["wire_system"]["health"],
            "guides_axes_h": ch["guides_axes"]["health"],
        })

    if len(trajectory) > 100:
        k = len(trajectory) // 100
        trajectory = trajectory[::k] + [trajectory[-1]]

    last = trajectory[-1]
    health_horizon = {
        "generator": {"health": last["generator_h"], "status": _status(last["generator_h"])},
        "dielectric": {"health": last["dielectric_h"], "status": _status(last["dielectric_h"])},
        "wire_system": {"health": last["wire_system_h"], "status": _status(last["wire_system_h"])},
        "guides_axes": {"health": last["guides_axes_h"], "status": _status(last["guides_axes_h"])},
        "overall": {"health": last["health"], "status": _status(last["health"])},
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
