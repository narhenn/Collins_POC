"""
physics.py — wire-cut EDM digital-twin physics.

A compact, first-principles model of a CNC wire electrical-discharge machine
(submerged dielectric, ~0.25 mm brass wire). Material is removed by a train of
controlled spark discharges across a servo-held gap between the travelling wire
electrode and the workpiece; eroded debris is swept away by a pressurised,
de-ionised dielectric.

Used two ways, exactly like the turbine twin:

  1. EXPECTED / RESIDUAL — given the measured generator + gap signals, compute
     what the physics says the cutting rate / gap behaviour *should* be. The
     residual (measured - expected) is the strongest instability signal: if the
     achieved cutting speed is far below what the discharge energy and spark
     frequency predict, the process has physically changed (poor flushing,
     contaminated dielectric, debris bridging) before any hard limit trips.

  2. FORWARD SIM — given a single "intensity" command (the programmed discharge
     aggressiveness, 0..1) plus a degradation/fault state, produce a physically
     consistent full telemetry frame. This lets the 3D / dashboard layer drive
     the twin with one control when it isn't streaming every raw sensor.

Pure stdlib (math + random). No platform imports, so it is reusable by the
behaviours, the ingestion service, the predictor, and tests alike.

Signal keys are the canonical CURIEs the rest of the platform uses.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

EDM = "edm:"

# Canonical signal keys for the wire-EDM twin. These are the live telemetry
# channels surfaced on the dashboard and watched by the behaviour rules.
SIGNALS = {
    "gap_v":        "edm:gapVoltage",            # average servo gap voltage (V)
    "peak_i":       "edm:peakCurrent",           # peak discharge current (A)
    "ton":          "edm:pulseOnTime",           # pulse on-time T_on (us)
    "toff":         "edm:pulseOffTime",          # pulse off-time T_off (us)
    "spark_freq":   "edm:sparkFrequency",        # effective discharge freq (kHz)
    "energy":       "edm:dischargeEnergy",       # energy per pulse (mJ)
    "wire_tension": "edm:wireTension",           # wire mechanical tension (N)
    "wire_feed":    "edm:wireFeedRate",          # wire spool feed speed (m/min)
    "wire_wear":    "edm:wireWear",              # wire/guide wear index (%)
    "cut_speed":    "edm:cuttingSpeed",          # area removal rate (mm2/min)
    "die_flow":     "edm:dielectricFlow",        # flushing flow (L/min)
    "die_press":    "edm:dielectricPressure",    # flushing pressure (bar)
    "die_temp":     "edm:dielectricTemperature", # dielectric tank temp (C)
    "die_cond":     "edm:dielectricConductivity",# dielectric conductivity (uS/cm)
    "short_rate":   "edm:shortCircuitRate",      # short-circuit pulse fraction (%)
    "spark_gap":    "edm:sparkGap",              # servo-held gap width (um)
    "ra":           "edm:surfaceRoughnessRa",    # achieved surface finish Ra (um)
    "break_risk":   "edm:wireBreakRisk",         # derived wire-break risk (%)
}

UNITS = {
    "edm:gapVoltage": "VOLT",
    "edm:peakCurrent": "A",
    "edm:pulseOnTime": "MicroSEC",
    "edm:pulseOffTime": "MicroSEC",
    "edm:sparkFrequency": "KiloHZ",
    "edm:dischargeEnergy": "MilliJ",
    "edm:wireTension": "N",
    "edm:wireFeedRate": "M-PER-MIN",
    "edm:wireWear": "PERCENT",
    "edm:cuttingSpeed": "MilliM2-PER-MIN",
    "edm:dielectricFlow": "L-PER-MIN",
    "edm:dielectricPressure": "BAR",
    "edm:dielectricTemperature": "DEG_C",
    "edm:dielectricConductivity": "MicroS-PER-CentiM",
    "edm:shortCircuitRate": "PERCENT",
    "edm:sparkGap": "MicroM",
    "edm:surfaceRoughnessRa": "MicroM",
    "edm:wireBreakRisk": "PERCENT",
}


@dataclass
class DesignPoint:
    """Nominal (healthy, mid-intensity) operating point of the machine."""
    gap_v: float = 52.0          # V   — working servo gap voltage
    open_v: float = 95.0         # V   — open-circuit ignition voltage
    peak_i: float = 18.0         # A   — peak discharge current at i=baseline
    ton: float = 1.2             # us  — pulse on-time
    toff: float = 12.0           # us  — pulse off-time
    wire_tension: float = 15.0   # N   — wire mechanical tension
    wire_feed: float = 9.0       # m/min — wire feed (continuous, consumed)
    die_flow: float = 6.0        # L/min — flushing flow
    die_press: float = 8.0       # bar — high-pressure flushing
    die_temp: float = 24.0       # C   — chiller-held dielectric temperature
    die_cond: float = 10.0       # uS/cm — de-ionised baseline conductivity
    spark_gap: float = 35.0      # um  — servo-held gap width
    ra: float = 1.5              # um  — baseline surface finish
    cut_speed: float = 150.0     # mm2/min — baseline area removal rate
    ambient: float = 22.0        # C   — shop ambient
    base_short: float = 0.03     # short-circuit fraction when healthy


@dataclass
class Redlines:
    # Limits are expressed in the SAME units the live frame reports, so the
    # behaviours / health all compare like-for-like (short_rate, break_risk and
    # wire_wear are reported as PERCENT in the frame).
    die_temp: float = 32.0       # C     — over: thermal instability / derate
    die_cond: float = 25.0       # uS/cm — over: weak gap insulation, unstable
    short_rate: float = 20.0     # %     — over: cut efficiency / quality collapse
    wire_tension_min: float = 6.0  # N    — below: wire whip / break
    break_risk: float = 70.0     # %     — over: imminent wire breakage
    gap_v_min: float = 25.0      # V     — below: persistent shorting
    die_press_min: float = 3.0   # bar   — below: flushing loss
    die_flow_min: float = 2.5    # L/min — below: flushing loss


redlines = Redlines()


@dataclass
class EDMState:
    """Slowly-varying internal state the forward sim integrates."""
    intensity: float = 0.55          # 0..1 programmed discharge aggressiveness
    guide_wear: float = 0.0          # 0..1 diamond guide / roller wear
    resin_depletion: float = 0.0     # 0..1 de-ioniser resin spent (cond rises)
    filter_clog: float = 0.0         # 0..1 dielectric filter clogging
    chiller_health: float = 1.0      # 1=ok 0=failed (dielectric temp control)
    debris: float = 0.05             # 0..1 debris concentration in the gap
    wire_wear: float = 0.0           # 0..1 wire/guide consumable wear index
    run_hours: float = 0.0
    fault: str = "none"              # injected fault id (see inject())
    fault_severity: float = 0.0      # 0..1
    extras: dict = field(default_factory=dict)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class EDMPhysics:
    """Stateless physics relations (expected/residual) + a stateful forward sim."""

    def __init__(self, design: DesignPoint | None = None,
                 limits: Redlines | None = None, seed: int = 0):
        self.d = design or DesignPoint()
        self.lim = limits or redlines
        self.rng = random.Random(seed)

    # ── 1. Pulse-train relations ─────────────────────────────────────

    def pulse_params(self, intensity: float) -> tuple[float, float, float, float]:
        """(peak_i, ton, toff, gap_v) for a programmed intensity.
        Higher intensity = more current, longer on-time, shorter off-time
        (faster cut, hotter, riskier)."""
        i = _clamp(intensity)
        peak_i = 8.0 + 26.0 * i
        ton = 0.6 + 1.8 * i
        toff = 18.0 - 10.0 * i
        gap_v = self.d.gap_v - 4.0 * i
        return peak_i, ton, toff, gap_v

    def discharge_energy(self, gap_v: float, peak_i: float, ton: float) -> float:
        """Energy per pulse in mJ:  E = V_gap * I_peak * T_on.
        (V·A·s -> J; T_on is in microseconds -> 1e-6, then ->mJ -> 1e3.)"""
        return gap_v * peak_i * ton * 1e-3

    def spark_frequency(self, ton: float, toff: float, debris: float) -> float:
        """Effective discharge frequency in kHz. The nominal period is
        (T_on+T_off); ignition delay and debris bridging stretch it, lowering
        the realised frequency."""
        ignition_delay = 2.0 + 6.0 * debris          # us — worse flushing, longer
        period_us = ton + toff + ignition_delay
        return 1.0e3 / period_us                      # 1e6/us = Hz -> /1e3 = kHz

    # ── 2. Process relations (expected behaviour) ────────────────────

    def expected_cut_speed(self, energy: float, freq: float, flush_eff: float,
                           short_rate: float) -> float:
        """Area removal rate (mm2/min) the physics predicts from the pulse
        train and flushing. Calibrated so the healthy design point lands on
        DesignPoint.cut_speed. Falls with short circuits and poor flushing."""
        raw = energy * freq                           # mJ·kHz ~ discharge power
        # Normalise so the healthy design-intensity baseline (energy~1.77 mJ,
        # freq~61 kHz) lands on DesignPoint.cut_speed.
        k = self.d.cut_speed / (1.77 * 61.0)
        return max(0.0, k * raw * flush_eff * (1.0 - short_rate))

    def expected_ra(self, energy: float, guide_wear: float) -> float:
        """Surface finish Ra (um) grows with crater size (~ energy^0.4); worn
        guides add wire wander that roughens the flank."""
        return 0.6 + 1.0 * (max(energy, 0.05) ** 0.4) + 1.2 * guide_wear

    def flush_efficiency(self, die_flow: float, die_press: float) -> float:
        """0..1 flushing effectiveness from flow and pressure vs design.
        Healthy flow+pressure give 1.0; clogging/pump loss drives it toward 0."""
        f = (die_flow / self.d.die_flow) * (die_press / self.d.die_press)
        return _clamp(f, 0.0, 1.0)

    def short_circuit_rate(self, debris: float, die_cond: float, spark_gap: float,
                           guide_wear: float) -> float:
        """0..1 fraction of pulses that collapse to a short. Rises with debris
        bridging, over-conductive dielectric, a too-small gap, and guide wear
        (wire wander)."""
        sc = self.d.base_short
        sc += 0.45 * debris
        sc += max(0.0, (die_cond - self.d.die_cond) / 40.0)
        sc += max(0.0, (self.d.spark_gap - spark_gap) / 60.0)
        sc += 0.20 * guide_wear
        return _clamp(sc)

    # ── 3. Residuals + health (the fault signal) ─────────────────────

    def residuals(self, measured: dict) -> dict:
        """measured: {signal_key: value}. Returns {signal_key: measured-expected}
        for the signals we can predict. Missing inputs fall back to design."""
        g = lambda k, dflt: float(measured.get(k, dflt))  # noqa: E731
        gap_v = g(SIGNALS["gap_v"], self.d.gap_v)
        peak_i = g(SIGNALS["peak_i"], self.d.peak_i)
        ton = g(SIGNALS["ton"], self.d.ton)
        toff = g(SIGNALS["toff"], self.d.toff)
        die_flow = g(SIGNALS["die_flow"], self.d.die_flow)
        die_press = g(SIGNALS["die_press"], self.d.die_press)
        out: dict[str, float] = {}
        energy = self.discharge_energy(gap_v, peak_i, ton)
        freq = g(SIGNALS["spark_freq"], self.spark_frequency(ton, toff, 0.05))
        flush = self.flush_efficiency(die_flow, die_press)
        # frame short_rate is a PERCENT; expected_cut_speed wants a fraction.
        sr = g(SIGNALS["short_rate"], self.d.base_short * 100.0) / 100.0
        if SIGNALS["cut_speed"] in measured:
            out[SIGNALS["cut_speed"]] = measured[SIGNALS["cut_speed"]] - \
                self.expected_cut_speed(energy, freq, flush, sr)
        if SIGNALS["ra"] in measured:
            out[SIGNALS["ra"]] = measured[SIGNALS["ra"]] - \
                self.expected_ra(energy, 0.0)
        return out

    def health_index(self, measured: dict) -> float:
        """0..1 overall process health from proximity to the key limits and the
        size of the cutting-speed residual. 1=healthy, 0=at/over several limits."""
        score = 1.0
        sr = measured.get(SIGNALS["short_rate"])
        if sr is not None:
            score -= _clamp(sr / self.lim.short_rate) * 0.30
        cond = measured.get(SIGNALS["die_cond"])
        if cond is not None:
            score -= _clamp(max(0.0, cond - self.d.die_cond) /
                            (self.lim.die_cond - self.d.die_cond)) * 0.20
        temp = measured.get(SIGNALS["die_temp"])
        if temp is not None:
            score -= _clamp(max(0.0, temp - self.d.die_temp) /
                            (self.lim.die_temp - self.d.die_temp)) * 0.15
        br = measured.get(SIGNALS["break_risk"])
        if br is not None:
            score -= _clamp(br / self.lim.break_risk) * 0.25
        cut = measured.get(SIGNALS["cut_speed"])
        if cut is not None:
            res = self.residuals(measured).get(SIGNALS["cut_speed"], 0.0)
            score -= min(0.20, abs(res) / 120.0)
        return _clamp(score)

    # ── 4. Forward simulation (intensity -> consistent frame) ────────

    def init_state(self, intensity: float = 0.55) -> EDMState:
        return EDMState(intensity=intensity)

    # Faults the forward sim understands.
    FAULTS = (
        "wire_break", "dielectric_contamination", "flushing_loss",
        "guide_wear", "chiller_failure", "servo_instability",
    )

    def inject(self, state: EDMState, fault: str, severity: float = 0.6) -> None:
        """Arm a fault for the forward sim (see FAULTS). Also seed the relevant
        degradation state so the fault is immediately visible on the LIVE feed
        (which advances in near real-time), then keep progressing from there."""
        state.fault = fault
        s = state.fault_severity = _clamp(severity)
        if fault == "flushing_loss":
            state.filter_clog = max(state.filter_clog, 0.40 * s)
        elif fault == "dielectric_contamination":
            state.resin_depletion = max(state.resin_depletion, 0.50 * s)
        elif fault == "guide_wear":
            state.guide_wear = max(state.guide_wear, 0.45 * s)
        elif fault == "chiller_failure":
            state.chiller_health = min(state.chiller_health, 1.0 - 0.50 * s)

    def forward(self, state: EDMState, dt: float = 1.0, noise: bool = True) -> dict:
        """Advance the machine `dt` seconds and return a consistent telemetry
        frame {signal_key: value}. Integrates slow degradation + any injected
        fault so a projection ramps toward the limit rather than jumping."""
        d = self.d
        dt_h = dt / 3600.0
        i = _clamp(state.intensity)

        # ── slow baseline degradation ──
        state.run_hours += dt_h
        state.resin_depletion = _clamp(state.resin_depletion + 0.010 * dt_h)
        state.filter_clog = _clamp(state.filter_clog + 0.008 * dt_h)
        state.guide_wear = _clamp(state.guide_wear + 0.004 * dt_h)
        state.wire_wear = _clamp(state.wire_wear + (0.5 + i) * 0.004 * dt_h)

        # ── injected faults progress over time, scaled by severity ──
        sev = state.fault_severity
        f = state.fault
        wire_break = False
        servo_unstable = False
        if f == "dielectric_contamination":
            state.resin_depletion = _clamp(state.resin_depletion + 2.4 * sev * dt_h)
        elif f == "flushing_loss":
            state.filter_clog = _clamp(state.filter_clog + 2.2 * sev * dt_h)
        elif f == "guide_wear":
            state.guide_wear = _clamp(state.guide_wear + 2.5 * sev * dt_h)
        elif f == "chiller_failure":
            state.chiller_health = _clamp(state.chiller_health - 2.0 * sev * dt_h)
        elif f == "servo_instability":
            servo_unstable = True
        elif f == "wire_break":
            wire_break = True

        # ── pulse train from intensity ──
        peak_i, ton, toff, gap_v = self.pulse_params(i)

        # ── dielectric system ──
        die_flow = d.die_flow * (1.0 - 0.6 * state.filter_clog)
        die_press = d.die_press * (1.0 - 0.7 * state.filter_clog)
        flush = self.flush_efficiency(die_flow, die_press)

        # debris relaxes toward an equilibrium set by cut load vs flushing
        debris_target = _clamp(0.05 + 0.7 * (1.0 - flush) + 0.3 * i * (1.0 - flush))
        state.debris += (debris_target - state.debris) * min(1.0, dt / 8.0)
        state.debris = _clamp(state.debris)
        debris = state.debris

        # discharge power heats the dielectric; chiller pulls it back to design
        energy = self.discharge_energy(gap_v, peak_i, ton)
        freq = self.spark_frequency(ton, toff, debris)
        discharge_pwr = energy * freq                      # ~ heat load proxy
        die_temp = (d.ambient
                    + (d.die_temp - d.ambient) * state.chiller_health
                    + discharge_pwr * 0.008
                    + (1.0 - state.chiller_health) * 12.0)

        # conductivity rises as resin depletes and the bath warms
        die_cond = (d.die_cond
                    + 30.0 * state.resin_depletion
                    + max(0.0, die_temp - d.die_temp) * 0.35)

        # servo-held gap shrinks with debris bridging and contamination
        spark_gap = d.spark_gap + 14.0 * i - 16.0 * debris \
            - max(0.0, die_cond - d.die_cond) * 0.20

        # ── gap stability ──
        short_rate = self.short_circuit_rate(debris, die_cond, spark_gap,
                                             state.guide_wear)
        if servo_unstable:
            short_rate = _clamp(short_rate + 0.30 * sev)
        # shorting drags the effective servo voltage down
        gap_v_eff = gap_v * (1.0 - 0.6 * short_rate)

        # ── wire mechanics ──
        wire_tension = d.wire_tension - 4.0 * state.guide_wear - 3.0 * state.wire_wear
        wire_feed = d.wire_feed + 1.5 * i
        if wire_break:
            wire_tension -= d.wire_tension * 0.7 * sev
            short_rate = _clamp(short_rate + 0.4 * sev)

        # ── process outputs ──
        cut_speed = self.expected_cut_speed(energy, freq, flush, short_rate)
        ra = self.expected_ra(energy, state.guide_wear)

        # wire-break risk: short circuits + tension loss + thermal + wear
        break_risk = _clamp(
            0.45 * short_rate
            + 0.30 * max(0.0, (self.lim.wire_tension_min - wire_tension)
                         / self.lim.wire_tension_min)
            + 0.20 * state.wire_wear
            + 0.10 * max(0.0, die_temp - d.die_temp) / 10.0
            + (0.5 * sev if wire_break else 0.0))

        if noise:
            gap_v_eff += self.rng.gauss(0, 0.6)
            peak_i += self.rng.gauss(0, 0.3)
            die_temp += self.rng.gauss(0, 0.15)
            die_cond += self.rng.gauss(0, 0.2)
            die_flow += self.rng.gauss(0, 0.05)
            die_press += self.rng.gauss(0, 0.05)
            cut_speed = max(0.0, cut_speed + self.rng.gauss(0, 1.5))
            short_rate = _clamp(short_rate + self.rng.gauss(0, 0.004))
            wire_tension += self.rng.gauss(0, 0.1)
            spark_gap += self.rng.gauss(0, 0.4)
            ra += self.rng.gauss(0, 0.02)

        return {
            SIGNALS["gap_v"]: round(max(0.0, gap_v_eff), 1),
            SIGNALS["peak_i"]: round(max(0.0, peak_i), 1),
            SIGNALS["ton"]: round(ton, 2),
            SIGNALS["toff"]: round(toff, 2),
            SIGNALS["spark_freq"]: round(freq, 1),
            SIGNALS["energy"]: round(energy, 3),
            SIGNALS["wire_tension"]: round(max(0.0, wire_tension), 2),
            SIGNALS["wire_feed"]: round(max(0.0, wire_feed), 2),
            SIGNALS["wire_wear"]: round(state.wire_wear * 100.0, 1),
            SIGNALS["cut_speed"]: round(cut_speed, 1),
            SIGNALS["die_flow"]: round(max(0.0, die_flow), 2),
            SIGNALS["die_press"]: round(max(0.0, die_press), 2),
            SIGNALS["die_temp"]: round(die_temp, 1),
            SIGNALS["die_cond"]: round(max(0.0, die_cond), 1),
            SIGNALS["short_rate"]: round(short_rate * 100.0, 1),
            SIGNALS["spark_gap"]: round(max(0.0, spark_gap), 1),
            SIGNALS["ra"]: round(max(0.0, ra), 2),
            SIGNALS["break_risk"]: round(break_risk * 100.0, 1),
        }
