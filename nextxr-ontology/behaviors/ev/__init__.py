"""
behaviors.ev — the behaviour rules that watch a GoalCert EV charging-site twin.

Tier-C hard-limit monitors across the four pillars: thermal-runaway risk, cell
over-temperature, transformer over-temp, grid overload, grid-headroom exhaustion,
HV-insulation loss, charger network uptime / faulted chargers, cell imbalance and
battery end-of-life. `build_ev_registry()` returns exactly these, used by both the
live engine and the forward predictor.
"""
from __future__ import annotations

from behaviors.registry import Behavior, Tier, TelemetrySample, Finding, BehaviorRegistry
from ev.physics import SIGNALS, redlines


class _Threshold(Behavior):
    """Data-driven one-shot threshold monitor (fires once on crossing, clears
    when the signal returns in-band, so a sustained fault is one finding)."""
    tier = Tier.C

    def __init__(self, behavior_id, signal, limit, direction, severity, unit, message):
        self.behavior_id = behavior_id
        self.watches = [signal]
        self.limit = limit
        self.direction = direction          # "above" | "below"
        self.severity = severity
        self.unit = unit
        self.message = message              # callable(value, limit) -> str
        self.reads = [f"{signal} in {unit}"]
        self.emits = f"A {severity} Finding when {signal} is {direction} {limit}."
        self._state: dict[str, dict] = {}

    def _over(self, value: float) -> bool:
        return value > self.limit if self.direction == "above" else value < self.limit

    def evaluate(self, sample: TelemetrySample, query) -> list[Finding]:
        st = self._state.setdefault(sample.entity_id, {"fired": False})
        if not self._over(sample.value):
            st["fired"] = False
            return []
        if st["fired"]:
            return []
        st["fired"] = True
        return [Finding(
            behavior_id=self.behavior_id, tier=self.tier, flags=sample.entity_id,
            severity=self.severity, message=self.message(sample.value, self.limit),
            confidence=1.0,
            evidence={"value": sample.value, "unit": self.unit, "limit": self.limit,
                      "signal": sample.signal})]


def build_ev_registry() -> BehaviorRegistry:
    r = BehaviorRegistry()
    rules = [
        _Threshold("ev.thermal_runaway", SIGNALS["runaway"], redlines.runaway, "above",
                   "critical", "%",
                   lambda v, l: (f"Thermal-runaway risk critical — {v:.0f}% (limit {l:.0f}%). "
                                 f"A cell is venting/off-gassing; isolate the pack, trigger "
                                 f"suppression and evacuate adjacent bays now.")),
        _Threshold("ev.cell_overtemp", SIGNALS["cell_temp"], redlines.cell_temp, "above",
                   "critical", "°C",
                   lambda v, l: (f"Cell temperature critical — {v:.0f}°C (limit {l:.0f}°C). "
                                 f"Cooling is losing the pack; derate charging and step up "
                                 f"coolant flow before a thermal event.")),
        _Threshold("ev.transformer_overtemp", SIGNALS["tx_temp"], redlines.tx_temp, "above",
                   "critical", "°C",
                   lambda v, l: (f"Transformer over-temperature — {v:.0f}°C (limit {l:.0f}°C). "
                                 f"Shed charging load / dispatch the BESS before insulation "
                                 f"aging accelerates.")),
        _Threshold("ev.grid_overload", SIGNALS["grid_load"], redlines.grid_load, "above",
                   "critical", "%",
                   lambda v, l: (f"Grid overload — site draw at {v:.0f}% of the transformer "
                                 f"limit ({l:.0f}%). EMS must curtail charging or peak-shave "
                                 f"from the BESS to avoid utility penalties.")),
        _Threshold("ev.headroom_low", SIGNALS["headroom"], redlines.headroom_min, "below",
                   "critical", "%",
                   lambda v, l: (f"Grid headroom exhausted — {v:.0f}% left (min {l:.0f}%). "
                                 f"No capacity for new sessions; queue arrivals and dispatch "
                                 f"storage.")),
        _Threshold("ev.insulation_low", SIGNALS["insulation"], redlines.insulation_min, "below",
                   "critical", "kΩ",
                   lambda v, l: (f"HV insulation low — {v:.0f} kΩ (min {l:.0f} kΩ). Isolation "
                                 f"fault risk; lock out the affected string and inspect for "
                                 f"moisture / cable damage.")),
        _Threshold("ev.uptime_low", SIGNALS["uptime"], redlines.uptime_min, "below",
                   "warning", "%",
                   lambda v, l: (f"Charger network uptime low — {v:.1f}% (SLA {l:.0f}%). "
                                 f"Run OCPP self-healing resets and schedule field service.")),
        _Threshold("ev.faulted_chargers", SIGNALS["faulted"], redlines.faulted_max, "above",
                   "warning", "",
                   lambda v, l: (f"{v:.0f} chargers faulted (threshold {l:.0f}). Utilisation and "
                                 f"revenue at risk — dispatch remote diagnostics before a truck roll.")),
        _Threshold("ev.cell_imbalance", SIGNALS["imbalance"], redlines.imbalance, "above",
                   "warning", "mV",
                   lambda v, l: (f"Cell imbalance high — {v:.0f} mV (limit {l:.0f} mV). "
                                 f"Dendrite-growth precursor; schedule a balancing cycle / module swap.")),
        _Threshold("ev.battery_eol", SIGNALS["soh"], redlines.soh_min, "below",
                   "warning", "%",
                   lambda v, l: (f"Fleet battery SoH low — {v:.0f}% (EoL {l:.0f}%). Plan pack "
                                 f"refurbishment; degraded packs cut range and raise thermal risk.")),
    ]
    for b in rules:
        try:
            r.register(b)
        except Exception:  # noqa: BLE001
            pass
    return r


__all__ = ["build_ev_registry"]
