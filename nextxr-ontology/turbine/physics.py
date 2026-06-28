"""
physics.py — gas-turbine digital-twin physics.

A compact, first-principles model of a two-spool gas turbine, used two ways:

  1. EXPECTED / RESIDUAL  — given measured sensors (+ ambient), compute what the
     physics says each signal *should* be. The residual (measured - expected) is
     the strongest fault signal: if EGT is 60 C above what fuel/N1 predict, the
     engine has physically changed (blade erosion, nozzle coking, seal leak).

  2. FORWARD SIM  — given a throttle command and a degradation/fault state,
     produce a physically consistent full sensor frame. This lets the 3D layer
     drive the twin with a single throttle (and optional injected fault) when it
     isn't streaming every raw sensor itself.

Pure stdlib (math + random). No platform imports, so it's reusable by the
behaviours, the ingestion service, and tests alike.

Signal keys are the canonical CURIEs the rest of the platform uses.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

AERO = "aero:"
CFP = "cfp:"

# Canonical signal keys for the turbine twin.
SIGNALS = {
    "egt": "aero:exhaustGasTemp",
    "n1": "aero:shaftSpeedN1",
    "n2": "aero:shaftSpeedN2",
    "fuel": "aero:fuelFlow",
    "vib": "aero:vibrationG",
    "epr": "aero:enginePressureRatio",
    "oil_temp": "aero:oilTemperature",
    "oil_press": "aero:oilPressure",
}

UNITS = {
    "aero:exhaustGasTemp": "DEG_C",
    "aero:shaftSpeedN1": "REV-PER-MIN",
    "aero:shaftSpeedN2": "REV-PER-MIN",
    "aero:fuelFlow": "KiloGM-PER-HR",
    "aero:vibrationG": "NUM",
    "aero:enginePressureRatio": "NUM",
    "aero:oilTemperature": "DEG_C",
    "aero:oilPressure": "PSI",
}


@dataclass
class DesignPoint:
    """Nominal (healthy, 100% thrust) operating point of the engine."""
    egt: float = 650.0           # C
    n1: float = 5200.0           # RPM (low-pressure spool)
    n2: float = 10200.0          # RPM (high-pressure spool)
    fuel: float = 800.0          # kg/h at full thrust
    fuel_idle: float = 220.0     # kg/h at idle
    epr: float = 1.62
    oil_temp: float = 70.0       # C
    oil_press: float = 55.0      # PSI
    vib: float = 0.30            # g
    ambient: float = 15.0        # C (ISA sea level)


@dataclass
class Redlines:
    egt: float = 780.0           # C  — hot-section limit
    n1: float = 5500.0           # RPM overspeed
    n2: float = 10800.0          # RPM overspeed
    oil_temp: float = 85.0       # C
    oil_press_min: float = 40.0  # PSI — below this is starvation
    vib: float = 2.0             # g  — bearing distress


redlines = Redlines()

# Brayton-style sensitivity exponents (calibrated, dimensionless).
ALPHA_FUEL = 0.30   # EGT ~ fuel^alpha
BETA_N1 = 0.20      # EGT ~ (N1_0/N1)^beta (more airflow cools)


@dataclass
class TurbineState:
    """Slowly-varying internal state the forward sim integrates."""
    throttle: float = 0.85               # 0..1 thrust demand
    condition: float = 1.0               # 1=new, 0=fully degraded (hot section)
    bearing_wear: float = 0.0            # 0..1
    oil_fouling: float = 0.0             # 0..1 (raises oil temp, lowers pressure)
    run_hours: float = 0.0
    fault: str = "none"                  # injected fault id (see inject())
    fault_severity: float = 0.0          # 0..1
    extras: dict = field(default_factory=dict)


class TurbinePhysics:
    """Stateless physics relations (expected/residual) + a stateful forward sim."""

    def __init__(self, design: DesignPoint | None = None,
                 limits: Redlines | None = None, seed: int = 0):
        self.d = design or DesignPoint()
        self.lim = limits or redlines
        self.rng = random.Random(seed)

    # ── 1. Physics expectation + residuals ───────────────────────────

    def expected_egt(self, fuel: float, n1: float, ambient: float | None = None,
                     condition: float = 1.0) -> float:
        """Brayton-cycle EGT prediction from fuel flow and N1.
        Degradation (condition<1) raises EGT for the same operating point."""
        amb = self.d.ambient if ambient is None else ambient
        fuel_ratio = max(fuel / self.d.fuel, 0.1)
        n1_ratio = max(self.d.n1 / max(n1, 100.0), 0.5)
        egt = self.d.egt * (fuel_ratio ** ALPHA_FUEL) * (n1_ratio ** BETA_N1)
        egt += (amb - self.d.ambient) * 0.6              # hotter day -> hotter EGT
        egt += (1.0 - condition) * (self.lim.egt - self.d.egt)
        return egt

    def expected_epr(self, n1: float, condition: float = 1.0) -> float:
        """EPR scales with corrected spool speed; degradation lowers it."""
        spool = max(n1 / self.d.n1, 0.2)
        return (1.0 + (self.d.epr - 1.0) * spool) * (0.85 + 0.15 * condition)

    def expected_oil_temp(self, n1: float, ambient: float | None = None,
                          fouling: float = 0.0) -> float:
        amb = self.d.ambient if ambient is None else ambient
        load = max(n1 / self.d.n1, 0.0)
        return amb + (self.d.oil_temp - self.d.ambient) * load + fouling * 25.0

    def residuals(self, measured: dict, ambient: float | None = None) -> dict:
        """measured: {signal_key: value}. Returns {signal_key: measured-expected}
        for the signals we can predict. Missing inputs fall back to design point."""
        get = lambda k, dflt: float(measured.get(k, dflt))  # noqa: E731
        fuel = get(SIGNALS["fuel"], self.d.fuel)
        n1 = get(SIGNALS["n1"], self.d.n1)
        out: dict[str, float] = {}
        if SIGNALS["egt"] in measured:
            out[SIGNALS["egt"]] = measured[SIGNALS["egt"]] - self.expected_egt(
                fuel, n1, ambient)
        if SIGNALS["epr"] in measured:
            out[SIGNALS["epr"]] = measured[SIGNALS["epr"]] - self.expected_epr(n1)
        if SIGNALS["oil_temp"] in measured:
            out[SIGNALS["oil_temp"]] = measured[SIGNALS["oil_temp"]] - \
                self.expected_oil_temp(n1, ambient)
        return out

    def health_index(self, measured: dict, ambient: float | None = None) -> float:
        """A 0..1 health score from how close key signals are to their limits and
        how large the EGT residual is. 1=healthy, 0=at/over multiple limits."""
        score = 1.0
        egt = measured.get(SIGNALS["egt"])
        if egt is not None:
            score -= max(0.0, (egt - self.d.egt) / (self.lim.egt - self.d.egt)) * 0.4
            res = self.residuals(measured, ambient).get(SIGNALS["egt"], 0.0)
            score -= min(0.3, abs(res) / 120.0)
        vib = measured.get(SIGNALS["vib"])
        if vib is not None:
            score -= max(0.0, (vib - self.d.vib) / (self.lim.vib - self.d.vib)) * 0.2
        op = measured.get(SIGNALS["oil_press"])
        if op is not None and op < self.d.oil_press:
            score -= min(0.2, (self.d.oil_press - op) /
                         (self.d.oil_press - self.lim.oil_press_min) * 0.2)
        return max(0.0, min(1.0, score))

    # ── 2. Forward simulation (throttle -> consistent sensor frame) ──

    def init_state(self, throttle: float = 0.85) -> TurbineState:
        return TurbineState(throttle=throttle)

    def inject(self, state: TurbineState, fault: str, severity: float = 0.6) -> None:
        """Arm a fault for the forward sim. Recognised faults:
        'blade_erosion', 'nozzle_coking', 'bearing_wear', 'oil_starvation',
        'compressor_fouling', 'surge'."""
        state.fault = fault
        state.fault_severity = max(0.0, min(1.0, severity))

    def forward(self, state: TurbineState, dt: float = 1.0,
                ambient: float | None = None, noise: bool = True) -> dict:
        """Advance the engine `dt` seconds and return a consistent sensor frame
        {signal_key: value}. Integrates slow degradation + any injected fault."""
        amb = self.d.ambient if ambient is None else ambient
        dt_h = dt / 3600.0
        thr = max(0.0, min(1.0, state.throttle))

        # baseline slow degradation
        state.run_hours += dt_h
        state.condition = max(0.0, state.condition - 0.0008 * dt_h)
        state.bearing_wear = min(1.0, state.bearing_wear + 0.0004 * dt_h)

        # Injected faults PROGRESS over time (accumulate into state, scaled by
        # severity and dt) so a projection ramps toward the limit rather than
        # jumping — giving a meaningful trajectory and time-to-failure.
        sev = state.fault_severity
        surge = False
        if state.fault == "blade_erosion":
            state.condition = max(0.05, state.condition - 2.5 * sev * dt_h)
        elif state.fault == "nozzle_coking":
            state.condition = max(0.10, state.condition - 1.8 * sev * dt_h)
        elif state.fault == "compressor_fouling":
            state.condition = max(0.15, state.condition - 1.5 * sev * dt_h)
        elif state.fault == "bearing_wear":
            state.bearing_wear = min(1.0, state.bearing_wear + 3.0 * sev * dt_h)
        elif state.fault == "oil_starvation":
            state.oil_fouling = min(1.0, state.oil_fouling + 2.5 * sev * dt_h)
        elif state.fault == "surge":
            surge = True
        cond = state.condition
        wear = state.bearing_wear
        fouling = state.oil_fouling

        # spool speeds follow throttle with a little droop from bearing friction
        n1 = (self.d.n1 * (0.55 + 0.45 * thr)) - wear * 45.0
        n2 = (self.d.n2 * (0.60 + 0.40 * thr)) - wear * 60.0

        # fuel follows throttle between idle and full; degradation needs more fuel
        fuel = self.d.fuel_idle + (self.d.fuel - self.d.fuel_idle) * thr
        fuel *= 1.0 + 0.15 * (1.0 - cond)

        egt = self.expected_egt(fuel, n1, amb, cond)
        epr = self.expected_epr(n1, cond)
        oil_temp = self.expected_oil_temp(n1, amb, fouling)
        oil_press = self.d.oil_press - fouling * 20.0 - wear * 8.0
        vib = self.d.vib + wear * 2.4 + (1.0 - cond) * 0.4

        if surge:
            # compressor surge: violent N1 fluctuation + EGT spike
            n1 -= self.d.n1 * 0.18 * sev
            egt += 90.0 * sev
            vib += 1.5 * sev

        if noise:
            egt += self.rng.gauss(0, 2.5)
            n1 += self.rng.gauss(0, 6.0)
            n2 += self.rng.gauss(0, 8.0)
            fuel += self.rng.gauss(0, 4.0)
            vib = max(0.0, vib + self.rng.gauss(0, 0.04))
            oil_temp += self.rng.gauss(0, 0.6)
            oil_press += self.rng.gauss(0, 0.8)
            epr += self.rng.gauss(0, 0.01)

        return {
            SIGNALS["egt"]: round(egt, 1),
            SIGNALS["n1"]: round(n1, 0),
            SIGNALS["n2"]: round(n2, 0),
            SIGNALS["fuel"]: round(fuel, 1),
            SIGNALS["vib"]: round(max(0.0, vib), 3),
            SIGNALS["epr"]: round(epr, 3),
            SIGNALS["oil_temp"]: round(oil_temp, 1),
            SIGNALS["oil_press"]: round(max(0.0, oil_press), 1),
        }
