"""
predict.py — the prediction engine for the GoalCert EV charging-site twin.

Same two jobs as the other twins, grounded in ev/physics.py:

  1. component_health(state, frame) — 0..1 health + status word per subsystem
     (charging network / battery / grid & EMS / solar & BESS / thermal).
  2. predict(start_state, horizon) — project the CURRENT trajectory forward
     (continuing whatever fault/degradation is active) and report the trajectory,
     now-vs-horizon subsystem health, the detection timeline, and time-to-limit
     (RUL) for each failure mode.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone, timedelta

from behaviors.registry import TelemetrySample
from behaviors.ev import build_ev_registry
from ev.physics import EVPhysics, EVState, SIGNALS, UNITS, redlines


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _status(h: float) -> str:
    return ("good" if h >= 0.8 else "fair" if h >= 0.6
            else "degraded" if h >= 0.4 else "critical")


def component_health(state: EVState, frame: dict, physics: EVPhysics) -> dict:
    """Per-subsystem health (0..1) with a status word."""
    lim = physics.lim
    g = lambda k, dflt: float(frame.get(SIGNALS[k], dflt))  # noqa: E731

    uptime = g("uptime", 99.0)
    faulted = g("faulted", 0.0)
    ocpp = g("ocpp", 240.0)
    soh = g("soh", 93.0)
    imbalance = g("imbalance", 14.0)
    cell_temp = g("cell_temp", 33.0)
    headroom = g("headroom", 32.0)
    tx_temp = g("tx_temp", 66.0)
    grid_load = g("grid_load", 68.0)
    solar = g("solar", 200.0)
    self_use = g("self_use", 63.0)
    bess_soc = g("bess_soc", 72.0)
    coolant = g("coolant", 29.0)
    runaway = g("runaway", 2.0)
    insulation = g("insulation", 1200.0)

    charger = _clamp(0.5 * _clamp((uptime - lim.uptime_min) / (100.0 - lim.uptime_min))
                     + 0.3 * _clamp(1 - faulted / lim.faulted_max)
                     + 0.2 * _clamp(1 - (ocpp - 240.0) / (lim.ocpp_max - 240.0)))
    battery = _clamp(0.5 * _clamp((soh - lim.soh_min) / (100.0 - lim.soh_min))
                     + 0.3 * _clamp(1 - imbalance / lim.imbalance)
                     + 0.2 * _clamp(1 - (cell_temp - 40.0) / (lim.cell_temp - 40.0)))
    grid = _clamp(0.5 * _clamp(headroom / 40.0)
                  + 0.3 * _clamp(1 - (tx_temp - lim.tx_temp_warn) / (lim.tx_temp - lim.tx_temp_warn))
                  + 0.2 * _clamp(1 - grid_load / lim.grid_load))
    energy = _clamp(0.4 * _clamp(self_use / 90.0)
                    + 0.3 * _clamp(bess_soc / 80.0)
                    + 0.3 * _clamp(solar / max(1.0, physics.d.solar_cap_kw * 0.7)))
    thermal = _clamp(0.5 * _clamp(1 - runaway / lim.runaway)
                     + 0.3 * _clamp(1 - (cell_temp - 40.0) / (lim.cell_temp - 40.0))
                     + 0.2 * _clamp(1 - (coolant - 30.0) / 20.0)
                     * _clamp(insulation / (lim.insulation_min * 4)))
    overall = physics.health_index(frame)

    out = {}
    for name, h in (("charger", charger), ("battery", battery), ("grid", grid),
                    ("energy", energy), ("thermal", thermal), ("overall", overall)):
        out[name] = {"health": round(h, 3), "status": _status(h)}
    return out


# Failure-mode limits tracked for RUL (direction relative to limit).
_LIMITS = [
    ("tx_overheat", SIGNALS["tx_temp"], "above", lambda: redlines.tx_temp,
     "transformer over-temperature"),
    ("grid_overload", SIGNALS["grid_load"], "above", lambda: redlines.grid_load,
     "grid overload limit"),
    ("thermal_runaway", SIGNALS["runaway"], "above", lambda: redlines.runaway,
     "thermal-runaway risk limit"),
    ("battery_eol", SIGNALS["soh"], "below", lambda: redlines.soh_min,
     "battery end-of-life (SoH)"),
    ("insulation_fault", SIGNALS["insulation"], "below", lambda: redlines.insulation_min,
     "HV insulation fault"),
    ("headroom_exhausted", SIGNALS["headroom"], "below", lambda: redlines.headroom_min,
     "grid headroom exhausted"),
]


def predict(start_state: EVState, horizon_min: float = 120.0,
            points: int = 120, physics: EVPhysics | None = None) -> dict:
    physics = physics or EVPhysics()
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
    registry = build_ev_registry()
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

        q_node.clear()
        q_node.update({k.split("#")[-1].split(":")[-1]: v for k, v in frame.items()})
        for sig, val in frame.items():
            s = TelemetrySample(signal=sig, entity_id="predict", value=float(val),
                                unit=UNITS.get(sig, ""),
                                timestamp=base + timedelta(seconds=i * step_s),
                                tenant_id="predict")
            for fnd in registry.evaluate(s, q):
                if fnd.behavior_id not in fired:
                    fired.add(fnd.behavior_id)
                    events.append({"t_min": t_min, "behavior_id": fnd.behavior_id,
                                   "severity": fnd.severity, "message": fnd.message})

        for key, sig, direction, lim_fn, _label in _LIMITS:
            if ttl[key] is None:
                v = frame.get(sig)
                lv = lim_fn()
                if v is not None and ((direction == "above" and v >= lv) or
                                      (direction == "below" and v <= lv)):
                    ttl[key] = t_min

        point = {"t_min": t_min, "health": ch["overall"]["health"],
                 "charger_h": ch["charger"]["health"], "battery_h": ch["battery"]["health"],
                 "grid_h": ch["grid"]["health"], "energy_h": ch["energy"]["health"],
                 "thermal_h": ch["thermal"]["health"]}
        point.update(frame)                     # ev: signal keys the charts plot
        trajectory.append(point)

    if len(trajectory) > 100:
        k = len(trajectory) // 100
        trajectory = trajectory[::k] + [trajectory[-1]]

    last = trajectory[-1]
    health_horizon = {name: {"health": last[f"{name}_h" if name != "overall" else "health"],
                             "status": _status(last[f"{name}_h" if name != "overall" else "health"])}
                      for name in ("charger", "battery", "grid", "energy", "thermal", "overall")}

    label_map = {k[0]: k[4] for k in _LIMITS}
    rul = [{"mode": label_map[key], "time_to_limit_min": t, "within_horizon": t is not None}
           for key, t in ttl.items()]

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
