"""
behaviors.edm — the behaviour rules that watch a wire-EDM twin.

Three-tier stack, same contract as the rest of the platform:

  * Tier A (physics)  — CutSpeedResidual: the achieved cutting rate vs what the
                        discharge energy / spark frequency / flushing predict.
                        The strongest early signal of a *process* problem
                        (poor flushing, contaminated dielectric, debris) before
                        any single channel trips a hard limit.
  * Tier C (rules)    — hard-limit monitors on the gap, dielectric, and wire:
                        short-circuit rate, dielectric over-temp / conductivity,
                        wire-break risk, wire-tension loss, flushing-pressure loss.

`build_edm_registry()` returns a registry of exactly these behaviours, used by
both the live ingest service and the forward predictor.
"""
from __future__ import annotations

from behaviors.registry import Behavior, Tier, TelemetrySample, Finding, BehaviorRegistry
from edm.physics import EDMPhysics, SIGNALS, redlines


# ── Tier A: process physics residual ─────────────────────────────────

class CutSpeedResidual(Behavior):
    """Predicts the cutting rate from the pulse train + flushing and fires when
    the achieved rate falls well short — i.e. energy is going in but material
    isn't coming off. That gap means the *process* has changed (flushing loss,
    dielectric contamination, debris bridging), not just the settings."""
    behavior_id = "edm.cut_speed_residual"
    tier = Tier.A
    watches = ["edm:cuttingSpeed"]
    reads = ["gap voltage, peak current, pulse on/off, flushing flow & pressure, "
             "short-circuit rate from the same entity (via graph query)"]
    emits = "A warning Finding when the cutting-rate shortfall exceeds the threshold."

    def __init__(self, shortfall_pct: float = 0.30):
        self.shortfall = shortfall_pct
        self.phys = EDMPhysics()
        self._firing: dict[str, bool] = {}

    def evaluate(self, sample: TelemetrySample, query) -> list[Finding]:
        ent = sample.entity_id
        d = self.phys.d
        node = {}
        try:
            node = query.get_node(sample.tenant_id, ent) or {}
        except Exception:
            node = {}

        def gp(local, dflt):
            try:
                return float(node.get(local, dflt))
            except Exception:
                return dflt

        gap_v = gp("gapVoltage", d.gap_v)
        peak_i = gp("peakCurrent", d.peak_i)
        ton = gp("pulseOnTime", d.ton)
        toff = gp("pulseOffTime", d.toff)
        flow = gp("dielectricFlow", d.die_flow)
        press = gp("dielectricPressure", d.die_press)
        short = gp("shortCircuitRate", d.base_short * 100.0) / 100.0

        energy = self.phys.discharge_energy(gap_v, peak_i, ton)
        freq = self.phys.spark_frequency(ton, toff, 0.05)
        flush = self.phys.flush_efficiency(flow, press)
        expected = self.phys.expected_cut_speed(energy, freq, flush, short)

        if expected <= 1e-6:
            return []
        shortfall = (expected - sample.value) / expected
        if shortfall <= self.shortfall:
            self._firing[ent] = False
            return []
        if self._firing.get(ent):
            return []
        self._firing[ent] = True

        return [Finding(
            behavior_id=self.behavior_id, tier=self.tier, flags=ent,
            severity="warning",
            message=(f"Cutting-rate shortfall — achieved {sample.value:.0f} vs "
                     f"predicted {expected:.0f} mm2/min ({shortfall*100:.0f}% below). "
                     f"Energy is going into the gap but removal has dropped: check "
                     f"flushing (flow/pressure), dielectric conductivity, and debris "
                     f"in the kerf before the wire destabilises."),
            confidence=min(1.0, shortfall / (self.shortfall * 2)),
            evidence={"achieved": sample.value, "predicted": round(expected, 1),
                      "shortfall_pct": round(shortfall * 100, 1),
                      "flush_eff": round(flush, 3), "short_rate_pct": round(short * 100, 1),
                      "signal": sample.signal})]


# ── Tier C: hard-limit threshold monitors ────────────────────────────

class _Threshold(Behavior):
    """Shared one-shot threshold machinery (fires once on crossing, clears
    when the signal returns in-band, so a sustained fault is one finding)."""
    tier = Tier.C

    def __init__(self, limit: float):
        self.limit = limit
        self._state: dict[str, dict] = {}

    def _over(self, value: float) -> bool:
        raise NotImplementedError

    def _finding(self, sample: TelemetrySample) -> Finding:
        raise NotImplementedError

    def evaluate(self, sample: TelemetrySample, query) -> list[Finding]:
        st = self._state.setdefault(sample.entity_id, {"fired": False})
        if not self._over(sample.value):
            st["fired"] = False
            return []
        if st["fired"]:
            return []
        st["fired"] = True
        return [self._finding(sample)]


class ShortCircuitHighRule(_Threshold):
    """Short-circuit pulse fraction over the stability limit."""
    behavior_id = "edm.short_circuit_high"
    watches = ["edm:shortCircuitRate"]
    reads = ["short-circuit pulse fraction in %"]
    emits = "A critical Finding when the short-circuit rate exceeds the limit."

    def __init__(self, max_pct: float = None):
        super().__init__(max_pct if max_pct is not None else redlines.short_rate)

    def _over(self, value):
        return value > self.limit

    def _finding(self, sample):
        return Finding(
            behavior_id=self.behavior_id, tier=self.tier, flags=sample.entity_id,
            severity="critical",
            message=(f"Short-circuit rate high — {sample.value:.0f}% "
                     f"(limit {self.limit:.0f}%). The gap is collapsing to shorts: "
                     f"material removal stalls and the wire is at risk. Back off feed, "
                     f"raise off-time, and restore flushing."),
            confidence=1.0,
            evidence={"value": sample.value, "unit": "%", "limit_pct": self.limit,
                      "signal": sample.signal})


class WireBreakRiskRule(_Threshold):
    """Derived wire-break risk over the imminent-failure limit."""
    behavior_id = "edm.wire_break_risk"
    watches = ["edm:wireBreakRisk"]
    reads = ["wire-break risk index in %"]
    emits = "A critical Finding when wire-break risk exceeds the limit."

    def __init__(self, max_pct: float = None):
        super().__init__(max_pct if max_pct is not None else redlines.break_risk)

    def _over(self, value):
        return value > self.limit

    def _finding(self, sample):
        return Finding(
            behavior_id=self.behavior_id, tier=self.tier, flags=sample.entity_id,
            severity="critical",
            message=(f"Wire-break risk high — {sample.value:.0f}% "
                     f"(limit {self.limit:.0f}%). A wire break will scrap the cut and "
                     f"stop the machine. Reduce discharge energy, check tension and "
                     f"flushing, and re-thread proactively if it keeps climbing."),
            confidence=1.0,
            evidence={"value": sample.value, "unit": "%", "limit_pct": self.limit,
                      "signal": sample.signal})


class WireTensionLowRule(_Threshold):
    """Wire mechanical tension below the stability minimum."""
    behavior_id = "edm.wire_tension_low"
    watches = ["edm:wireTension"]
    reads = ["wire tension in N"]
    emits = "A critical Finding when wire tension drops below the minimum."

    def __init__(self, min_n: float = None):
        super().__init__(min_n if min_n is not None else redlines.wire_tension_min)

    def _over(self, value):
        return value < self.limit

    def _finding(self, sample):
        return Finding(
            behavior_id=self.behavior_id, tier=self.tier, flags=sample.entity_id,
            severity="critical",
            message=(f"Wire tension low — {sample.value:.1f} N "
                     f"(minimum {self.limit:.1f} N). The wire will whip and wander, "
                     f"hurting accuracy and risking a break. Check the tension servo, "
                     f"brake, and guide condition."),
            confidence=1.0,
            evidence={"value": sample.value, "unit": "N", "min_n": self.limit,
                      "signal": sample.signal})


class DielectricOverTempRule(_Threshold):
    """Dielectric tank temperature over limit (chiller / thermal instability)."""
    behavior_id = "edm.dielectric_overtemp"
    watches = ["edm:dielectricTemperature"]
    reads = ["dielectric temperature in C"]
    emits = "A warning Finding when dielectric temperature exceeds the limit."

    def __init__(self, max_c: float = None):
        super().__init__(max_c if max_c is not None else redlines.die_temp)

    def _over(self, value):
        return value > self.limit

    def _finding(self, sample):
        return Finding(
            behavior_id=self.behavior_id, tier=self.tier, flags=sample.entity_id,
            severity="warning",
            message=(f"Dielectric over-temperature — {sample.value:.1f} C "
                     f"(limit {self.limit:.1f} C). Warm dielectric loses insulating "
                     f"strength and conductivity climbs, destabilising the gap. Check "
                     f"the chiller and bath circulation."),
            confidence=1.0,
            evidence={"value": sample.value, "unit": "DEG_C", "limit_c": self.limit,
                      "signal": sample.signal})


class DielectricConductivityHighRule(_Threshold):
    """Dielectric conductivity over limit (de-ioniser resin spent)."""
    behavior_id = "edm.dielectric_conductivity_high"
    watches = ["edm:dielectricConductivity"]
    reads = ["dielectric conductivity in uS/cm"]
    emits = "A warning Finding when dielectric conductivity exceeds the limit."

    def __init__(self, max_us: float = None):
        super().__init__(max_us if max_us is not None else redlines.die_cond)

    def _over(self, value):
        return value > self.limit

    def _finding(self, sample):
        return Finding(
            behavior_id=self.behavior_id, tier=self.tier, flags=sample.entity_id,
            severity="warning",
            message=(f"Dielectric conductivity high — {sample.value:.0f} uS/cm "
                     f"(limit {self.limit:.0f} uS/cm). The bath is no longer "
                     f"de-ionised enough to hold off the gap; expect erratic ignition "
                     f"and more short circuits. Service the de-ioniser resin."),
            confidence=1.0,
            evidence={"value": sample.value, "unit": "uS/cm", "limit_us": self.limit,
                      "signal": sample.signal})


class FlushingPressureLowRule(_Threshold):
    """Flushing pressure below the minimum (filter clog / pump)."""
    behavior_id = "edm.flushing_pressure_low"
    watches = ["edm:dielectricPressure"]
    reads = ["flushing pressure in bar"]
    emits = "A warning Finding when flushing pressure drops below the minimum."

    def __init__(self, min_bar: float = None):
        super().__init__(min_bar if min_bar is not None else redlines.die_press_min)

    def _over(self, value):
        return value < self.limit

    def _finding(self, sample):
        return Finding(
            behavior_id=self.behavior_id, tier=self.tier, flags=sample.entity_id,
            severity="warning",
            message=(f"Flushing pressure low — {sample.value:.1f} bar "
                     f"(minimum {self.limit:.1f} bar). Debris is no longer being swept "
                     f"from the kerf, so cuts slow and short circuits rise. Check the "
                     f"flushing pump and replace the dielectric filter."),
            confidence=1.0,
            evidence={"value": sample.value, "unit": "bar", "min_bar": self.limit,
                      "signal": sample.signal})


def build_edm_registry() -> BehaviorRegistry:
    """A registry of exactly the behaviours that watch wire-EDM signals."""
    r = BehaviorRegistry()
    for b in (CutSpeedResidual(), ShortCircuitHighRule(), WireBreakRiskRule(),
              WireTensionLowRule(), DielectricOverTempRule(),
              DielectricConductivityHighRule(), FlushingPressureLowRule()):
        try:
            r.register(b)
        except Exception:  # noqa: BLE001 — duplicate id, skip
            pass
    return r


__all__ = [
    "CutSpeedResidual", "ShortCircuitHighRule", "WireBreakRiskRule",
    "WireTensionLowRule", "DielectricOverTempRule",
    "DielectricConductivityHighRule", "FlushingPressureLowRule",
    "build_edm_registry",
]
