"""
Aerospace Tier-C rules: turbine threshold monitors.

Hard-limit detectors for the gas-turbine twin — EGT redline, oil over-temp,
oil-pressure starvation, and bearing vibration. Each fires once on crossing its
limit (hysteresis) and clears when the signal returns in-band, so a sustained
fault produces one finding, not a storm.

Thresholds default to the turbine physics redlines (turbine/physics.py).
"""
from behaviors.registry import Behavior, Tier, TelemetrySample, Finding


class _Threshold(Behavior):
    """Shared one-shot threshold machinery."""
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


class EGTRedlineRule(_Threshold):
    """Exhaust gas temperature over the hot-section redline."""
    behavior_id = "aero.egt_redline"
    watches = ["aero:exhaustGasTemp"]
    reads = ["exhaust gas temperature in C"]
    emits = "A critical Finding when EGT exceeds the redline."

    def __init__(self, redline_c: float = 780.0):
        super().__init__(redline_c)

    def _over(self, value):
        return value > self.limit

    def _finding(self, sample):
        return Finding(
            behavior_id=self.behavior_id, tier=self.tier, flags=sample.entity_id,
            severity="critical",
            message=(f"EGT redline exceeded — {sample.value:.0f} C "
                     f"(redline {self.limit:.0f} C). Hot-section overheat: reduce "
                     f"thrust immediately and inspect turbine blades / fuel nozzles."),
            confidence=1.0,
            evidence={"value": sample.value, "unit": "DEG_C",
                      "redline_c": self.limit, "signal": sample.signal})


class OilTempOverTempRule(_Threshold):
    """Lubrication oil temperature over limit (bearing distress / oil break-down)."""
    behavior_id = "aero.oil_overtemp"
    watches = ["aero:oilTemperature"]
    reads = ["oil temperature in C"]
    emits = "A warning Finding when oil temperature exceeds the limit."

    def __init__(self, max_c: float = 85.0):
        super().__init__(max_c)

    def _over(self, value):
        return value > self.limit

    def _finding(self, sample):
        return Finding(
            behavior_id=self.behavior_id, tier=self.tier, flags=sample.entity_id,
            severity="warning",
            message=(f"Oil over-temperature — {sample.value:.0f} C "
                     f"(limit {self.limit:.0f} C). Lubrication is degrading; check "
                     f"oil cooler and bearing condition before continued running."),
            confidence=1.0,
            evidence={"value": sample.value, "unit": "DEG_C",
                      "limit_c": self.limit, "signal": sample.signal})


class OilPressureLowRule(_Threshold):
    """Lubrication oil pressure below the starvation limit."""
    behavior_id = "aero.oil_pressure_low"
    watches = ["aero:oilPressure"]
    reads = ["oil pressure in PSI"]
    emits = "A critical Finding when oil pressure drops below the minimum."

    def __init__(self, min_psi: float = 40.0):
        super().__init__(min_psi)

    def _over(self, value):
        return value < self.limit

    def _finding(self, sample):
        return Finding(
            behavior_id=self.behavior_id, tier=self.tier, flags=sample.entity_id,
            severity="critical",
            message=(f"Oil pressure low — {sample.value:.0f} PSI "
                     f"(minimum {self.limit:.0f} PSI). Risk of bearing starvation; "
                     f"shut down to avoid bearing failure."),
            confidence=1.0,
            evidence={"value": sample.value, "unit": "PSI",
                      "min_psi": self.limit, "signal": sample.signal})


class VibrationHighRule(_Threshold):
    """Shaft vibration over the bearing-distress limit."""
    behavior_id = "aero.vibration_high"
    watches = ["aero:vibrationG"]
    reads = ["shaft vibration in g"]
    emits = "A warning Finding when vibration exceeds the limit."

    def __init__(self, max_g: float = 2.0):
        super().__init__(max_g)

    def _over(self, value):
        return value > self.limit

    def _finding(self, sample):
        return Finding(
            behavior_id=self.behavior_id, tier=self.tier, flags=sample.entity_id,
            severity="warning",
            message=(f"High shaft vibration — {sample.value:.2f} g "
                     f"(limit {self.limit:.2f} g). Indicates rotor imbalance or "
                     f"bearing wear; trend closely and plan a borescope."),
            confidence=1.0,
            evidence={"value": sample.value, "unit": "g",
                      "limit_g": self.limit, "signal": sample.signal})
