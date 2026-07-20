"""
physics.py — GoalCert EV charging + energy-site digital-twin physics.

A compact, first-principles model of a commercial charging hub that GoalCert
orchestrates: a bank of DC-fast + AC bays streaming OCPP telemetry, an on-site
BESS and solar canopy, and a grid transformer held under a fixed site limit by
the EMS. Driven by ONE control — `demand` (0..1 site charging demand) — plus a
slow degradation/fault state, it produces a physically consistent frame across
the four GoalCert pillars (SitePredict is planning-side, so not simulated here).

Used exactly like the EDM / turbine / fleet twins:

  1. FORWARD SIM — demand + fault state -> a full, coupled telemetry frame.
  2. RESIDUAL   — the EMS "expected grid draw" vs the achieved draw (peak-shave
                  effectiveness) is the earliest sign the site is losing headroom.

Pure stdlib (math + random). Signal keys are the canonical `ev:` CURIEs the rest
of the platform (and the web app) uses.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

EV = "ev:"

# Canonical signal keys — the live channels shown on the dashboard / 3-D world
# and watched by the behaviour rules. Values match the web app's `ev:` keys.
SIGNALS = {
    # Pillar II — Charging management (OCPP)
    "uptime":       "ev:chargerUptime",
    "utilization":  "ev:utilization",
    "sessions":     "ev:sessionsActive",
    "faulted":      "ev:faultedChargers",
    "ocpp":         "ev:ocppLatency",
    "queue":        "ev:queueWait",
    "power":        "ev:chargingPower",
    # Pillar IV — Energy management (EMS / grid)
    "grid_load":    "ev:gridLoad",
    "headroom":     "ev:loadHeadroom",
    "peak":         "ev:peakDemand",
    "tx_temp":      "ev:transformerTemp",
    "bess_soc":     "ev:bessSoc",
    "bess_power":   "ev:bessPower",
    "solar":        "ev:solarOutput",
    "self_use":     "ev:selfConsumption",
    "v2g":          "ev:v2gCapacity",
    # Pillar III — Fleet & battery health
    "soc":          "ev:stateOfCharge",
    "soh":          "ev:stateOfHealth",
    "cell_temp":    "ev:cellTempMax",
    "imbalance":    "ev:cellImbalance",
    "coolant":      "ev:coolantTemp",
    "insulation":   "ev:insulationResistance",
    "runaway":      "ev:thermalRunawayRisk",
    # Commercial
    "revenue":      "ev:revenueToday",
    "tariff":       "ev:tariffRate",
    "energy":       "ev:energyToday",
    "co2":          "ev:co2Avoided",
}

UNITS = {
    "ev:chargerUptime": "PERCENT", "ev:utilization": "PERCENT", "ev:sessionsActive": "",
    "ev:faultedChargers": "", "ev:ocppLatency": "MilliSEC", "ev:queueWait": "MIN",
    "ev:chargingPower": "KiloW", "ev:gridLoad": "PERCENT", "ev:loadHeadroom": "PERCENT",
    "ev:peakDemand": "KiloW", "ev:transformerTemp": "DEG_C", "ev:bessSoc": "PERCENT",
    "ev:bessPower": "KiloW", "ev:solarOutput": "KiloW", "ev:selfConsumption": "PERCENT",
    "ev:v2gCapacity": "KiloWH", "ev:stateOfCharge": "PERCENT", "ev:stateOfHealth": "PERCENT",
    "ev:cellTempMax": "DEG_C", "ev:cellImbalance": "MilliV", "ev:coolantTemp": "DEG_C",
    "ev:insulationResistance": "KiloOHM", "ev:thermalRunawayRisk": "PERCENT",
    "ev:revenueToday": "INR-K", "ev:tariffRate": "INR-PER-KWH", "ev:energyToday": "MegaWH",
    "ev:co2Avoided": "KG",
}


@dataclass
class DesignPoint:
    """Nominal site design — a mid-size commercial charging hub."""
    site_limit_kw: float = 550.0     # transformer usable limit (630 kVA)
    building_base_kw: float = 160.0  # host-property base load
    solar_cap_kw: float = 320.0      # PV canopy nameplate
    bess_max_kw: float = 200.0       # BESS inverter power
    bess_capacity_kwh: float = 1200.0
    n_bays: int = 24                 # charging bays
    avg_session_kw: float = 34.0     # mixed DC/AC per-session draw
    co2_factor: float = 0.9          # kg CO2 avoided per delivered kWh (vs ICE)


@dataclass
class Redlines:
    # Expressed in the SAME units the live frame reports.
    tx_temp: float = 105.0           # C  — transformer hot-spot limit
    tx_temp_warn: float = 85.0
    grid_load: float = 95.0          # %  — over: overload / peak penalties
    headroom_min: float = 5.0        # %  — below: no capacity left
    uptime_min: float = 90.0         # %  — below: SLA breach
    faulted_max: float = 5.0         # count — over: fleet reliability breach
    cell_temp: float = 55.0          # C  — over: thermal event
    runaway: float = 40.0            # %  — over: imminent thermal runaway
    imbalance: float = 60.0          # mV — over: dendrite / cell failure
    soh_min: float = 74.0            # %  — below: battery end-of-life
    insulation_min: float = 100.0    # kΩ — below: HV insulation fault
    ocpp_max: float = 1500.0         # ms — over: comms fault


redlines = Redlines()


@dataclass
class EVState:
    """Slowly-varying internal state the forward sim integrates."""
    demand: float = 0.46             # 0..1 control — site charging demand level
    soh_wear: float = 0.07           # 0..1 fleet battery degradation (SoH=100-100*wear)
    charger_fault: float = 0.0       # 0..1 EVSE fleet fault level (uptime / OCPP)
    n_faulted: float = 0.0           # faulted charger count
    tx_aging: float = 0.0            # 0..1 transformer thermal aging
    insul_deg: float = 0.0           # 0..1 HV insulation degradation
    solar_derate: float = 0.0        # 0..1 solar loss (hot cell / soiling)
    v2g_loss: float = 0.0            # 0..1 loss of V2G / BESS dispatch capability
    runaway_seed: float = 0.0        # 0..1 thermal-runaway precursor
    bess_soc: float = 72.0           # %
    energy_today: float = 5.8        # MWh accumulator
    revenue_today: float = 148.0     # ₹k accumulator
    co2_today: float = 2100.0        # kg accumulator
    tod: float = 0.46                # time-of-day phase 0..1 (drives solar + tariff)
    run_hours: float = 0.0
    fault: str = "none"
    fault_severity: float = 0.0
    extras: dict = field(default_factory=dict)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class EVPhysics:
    """Stateless relations + a stateful forward sim for the charging site."""

    FAULTS = (
        "thermal_runaway", "grid_overload", "charger_fault", "battery_degradation",
        "connector_stuck", "insulation_fault", "solar_hotcell", "v2g_failure",
    )

    def __init__(self, design: DesignPoint | None = None,
                 limits: Redlines | None = None, seed: int = 0, **_ignored):
        self.d = design or DesignPoint()
        self.lim = limits or redlines
        self.rng = random.Random(seed)

    # ── control ──
    def init_state(self, demand: float = 0.46) -> EVState:
        return EVState(demand=demand)

    # ── daylight bell (0..1) from the time-of-day phase ──
    def _irradiance(self, tod: float) -> float:
        # daylight roughly between tod 0.25 (06:00) and 0.79 (19:00)
        x = (tod - 0.27) / 0.5
        return max(0.0, math.sin(math.pi * x)) if 0.0 <= x <= 1.0 else 0.0

    # ── expected grid draw (the EMS target) — for the residual ──
    def expected_grid_draw(self, charging_power: float, solar: float) -> float:
        """What the EMS expects to draw from the grid after solar offset and a
        nominal BESS shave. The residual (achieved-expected) exposes shave loss."""
        gross = charging_power + self.d.building_base_kw - solar
        shave = min(self.d.bess_max_kw, max(0.0, gross - self.d.site_limit_kw * 0.9))
        return max(0.0, gross - shave)

    def inject(self, state: EVState, fault: str, severity: float = 0.6) -> None:
        """Arm a fault for the forward sim and seed the relevant degradation so
        it's immediately visible on the near-real-time feed, then progresses."""
        state.fault = fault
        s = state.fault_severity = _clamp(severity)
        if fault == "thermal_runaway":
            state.runaway_seed = max(state.runaway_seed, 0.55 * s)
        elif fault == "grid_overload":
            state.demand = min(1.0, state.demand + 0.42 * s)
        elif fault == "charger_fault":
            state.charger_fault = max(state.charger_fault, 0.55 * s)
            state.n_faulted = max(state.n_faulted, round(6 * s))
        elif fault == "battery_degradation":
            state.soh_wear = _clamp(state.soh_wear + 0.18 * s)
        elif fault == "connector_stuck":
            state.n_faulted = max(state.n_faulted, round(3 * s))
            state.charger_fault = max(state.charger_fault, 0.22 * s)
        elif fault == "insulation_fault":
            state.insul_deg = max(state.insul_deg, 0.7 * s)
        elif fault == "solar_hotcell":
            state.solar_derate = max(state.solar_derate, 0.6 * s)
        elif fault == "v2g_failure":
            state.v2g_loss = max(state.v2g_loss, 0.7 * s)

    def forward(self, state: EVState, dt: float = 1.0, noise: bool = True) -> dict:
        """Advance the site `dt` seconds and return a coupled telemetry frame."""
        d, lim = self.d, self.lim
        dt_h = dt / 3600.0
        i = _clamp(state.demand)

        # ── time + slow baseline aging ──
        state.run_hours += dt_h
        state.tod = (state.tod + dt_h / 24.0) % 1.0
        state.soh_wear = _clamp(state.soh_wear + 0.0016 * dt_h)
        state.tx_aging = _clamp(state.tx_aging + 0.0010 * dt_h)

        # ── injected faults progress over time (scaled by severity) ──
        sev, f = state.fault_severity, state.fault
        if f == "thermal_runaway":
            state.runaway_seed = _clamp(state.runaway_seed + 2.4 * sev * dt_h)
        elif f == "charger_fault":
            state.charger_fault = _clamp(state.charger_fault + 1.6 * sev * dt_h)
        elif f == "battery_degradation":
            state.soh_wear = _clamp(state.soh_wear + 1.2 * sev * dt_h)
        elif f == "insulation_fault":
            state.insul_deg = _clamp(state.insul_deg + 1.8 * sev * dt_h)
        elif f == "solar_hotcell":
            state.solar_derate = _clamp(state.solar_derate + 1.2 * sev * dt_h)
        elif f == "v2g_failure":
            state.v2g_loss = _clamp(state.v2g_loss + 1.4 * sev * dt_h)

        # ── charging network (OCPP) ──
        n_raw = 6.0 + 20.0 * i
        n_sessions = max(0.0, n_raw - state.n_faulted * 0.8 - 8.0 * state.charger_fault)
        charging_power = n_sessions * d.avg_session_kw * (0.9 + 0.2 * i)
        utilization = _clamp(n_sessions / d.n_bays) * 100.0
        uptime = 100.0 - 9.0 * state.charger_fault - 1.4 - 0.6 * state.n_faulted
        faulted = round(state.n_faulted)
        ocpp = 240.0 + 1450.0 * state.charger_fault
        queue = max(0.0, n_sessions - d.n_bays * 0.8) * 2.4 + 4.0 * state.charger_fault

        # ── on-site solar ──
        irr = self._irradiance(state.tod)
        solar = d.solar_cap_kw * irr * (1.0 - state.solar_derate)
        load_for_solar = charging_power + d.building_base_kw
        self_use = _clamp(min(solar, load_for_solar) / solar) * 100.0 if solar > 1.0 else 72.0

        # ── EMS: grid draw + BESS peak-shave / solar-charge ──
        gross = charging_power + d.building_base_kw - solar
        bess_power = 0.0
        if gross > d.site_limit_kw * 0.9 and state.bess_soc > 10.0:
            # discharge to shave the peak (limited by inverter + V2G/BESS health)
            discharge = min(d.bess_max_kw * (1.0 - state.v2g_loss),
                            gross - d.site_limit_kw * 0.9)
            bess_power = -discharge
            state.bess_soc = max(0.0, state.bess_soc - discharge * dt_h / d.bess_capacity_kwh * 100.0)
        elif solar > charging_power and state.bess_soc < 95.0:
            # soak surplus solar into the BESS
            charge = min(d.bess_max_kw, (solar - charging_power) * 0.5)
            bess_power = charge
            state.bess_soc = min(100.0, state.bess_soc + charge * dt_h / d.bess_capacity_kwh * 100.0)
        grid_draw = max(0.0, gross + bess_power)      # + charge adds load, - discharge sheds it
        grid_load = grid_draw / d.site_limit_kw * 100.0
        headroom = max(0.0, (d.site_limit_kw - grid_draw) / d.site_limit_kw * 100.0)
        peak = grid_draw
        tx_temp = (40.0 + (grid_load / 100.0) * 42.0 + state.tx_aging * 18.0
                   + (18.0 * sev if f == "grid_overload" else 0.0))

        # ── battery (fleet + BESS aggregate) ──
        soh = max(55.0, 100.0 - state.soh_wear * 100.0)
        soc = 64.0 + 6.0 * math.sin(state.tod * 2 * math.pi) - state.soh_wear * 40.0
        cell_temp = (28.0 + 0.008 * charging_power + 22.0 * state.runaway_seed
                     + max(0.0, tx_temp - 70.0) * 0.15)
        imbalance = 12.0 + 62.0 * state.runaway_seed + state.soh_wear * 90.0
        coolant = 26.0 + 0.004 * charging_power + 14.0 * state.runaway_seed
        insulation = max(25.0, 1300.0 - 1250.0 * state.insul_deg)
        runaway = _clamp(
            (2.0 + 60.0 * state.runaway_seed
             + max(0.0, cell_temp - 42.0) * 4.0
             + max(0.0, imbalance - 30.0) * 0.7
             + max(0.0, lim.insulation_min - insulation) * 0.02) / 100.0) * 100.0

        # ── commercial (accumulators over the day) ──
        peak_tou = 0.5 + 0.5 * math.sin((state.tod - 0.58) * 2 * math.pi)   # evening peak
        tariff = 8.5 + 3.0 * _clamp(peak_tou) + 3.0 * _clamp((grid_load - 60.0) / 40.0)
        kwh = charging_power * dt_h
        state.energy_today += kwh / 1000.0                     # MWh
        state.revenue_today += kwh * tariff / 1000.0           # ₹k
        state.co2_today += kwh * d.co2_factor                  # kg
        v2g = max(0.0, 340.0 * (1.0 - state.v2g_loss) * (state.bess_soc / 72.0))

        if noise:
            g = self.rng.gauss
            uptime += g(0, 0.15); utilization += g(0, 1.2); charging_power = max(0.0, charging_power + g(0, 8))
            ocpp += g(0, 25); grid_load += g(0, 0.8); tx_temp += g(0, 0.3)
            cell_temp += g(0, 0.25); imbalance += g(0, 1.2); coolant += g(0, 0.2)
            soc += g(0, 0.6); solar = max(0.0, solar + g(0, 4)); peak = max(0.0, peak + g(0, 4))
            tariff += g(0, 0.15)

        return {
            SIGNALS["uptime"]: round(_clamp(uptime / 100.0, 0.0, 1.0) * 100.0, 1),
            SIGNALS["utilization"]: round(max(0.0, utilization), 1),
            SIGNALS["sessions"]: int(round(max(0.0, n_sessions))),
            SIGNALS["faulted"]: int(faulted),
            SIGNALS["ocpp"]: round(max(0.0, ocpp), 0),
            SIGNALS["queue"]: round(max(0.0, queue), 1),
            SIGNALS["power"]: round(max(0.0, charging_power), 0),
            SIGNALS["grid_load"]: round(max(0.0, grid_load), 1),
            SIGNALS["headroom"]: round(headroom, 1),
            SIGNALS["peak"]: round(peak, 0),
            SIGNALS["tx_temp"]: round(tx_temp, 1),
            SIGNALS["bess_soc"]: round(state.bess_soc, 1),
            SIGNALS["bess_power"]: round(bess_power, 0),
            SIGNALS["solar"]: round(solar, 0),
            SIGNALS["self_use"]: round(_clamp(self_use / 100.0) * 100.0, 1),
            SIGNALS["v2g"]: round(v2g, 0),
            SIGNALS["soc"]: round(max(0.0, min(100.0, soc)), 1),
            SIGNALS["soh"]: round(soh, 1),
            SIGNALS["cell_temp"]: round(cell_temp, 1),
            SIGNALS["imbalance"]: round(max(0.0, imbalance), 0),
            SIGNALS["coolant"]: round(coolant, 1),
            SIGNALS["insulation"]: round(insulation, 0),
            SIGNALS["runaway"]: round(runaway, 1),
            SIGNALS["revenue"]: round(state.revenue_today, 0),
            SIGNALS["tariff"]: round(tariff, 1),
            SIGNALS["energy"]: round(state.energy_today, 2),
            SIGNALS["co2"]: round(state.co2_today, 0),
        }

    # ── residual + health ──
    def residuals(self, measured: dict) -> dict:
        power = float(measured.get(SIGNALS["power"], 0.0))
        solar = float(measured.get(SIGNALS["solar"], 0.0))
        peak = measured.get(SIGNALS["peak"])
        if peak is None:
            return {}
        expected = self.expected_grid_draw(power, solar)
        return {SIGNALS["peak"]: round(float(peak) - expected, 1)}

    def health_index(self, measured: dict) -> float:
        """0..1 site health from proximity to the key limits."""
        lim = self.lim
        score = 1.0
        g = lambda k: measured.get(SIGNALS[k])  # noqa: E731

        up = g("uptime")
        if up is not None:
            score -= _clamp((lim.uptime_min + 6 - up) / 12.0) * 0.14
        head = g("headroom")
        if head is not None:
            score -= _clamp((lim.headroom_min + 20 - head) / 25.0) * 0.16
        tx = g("tx_temp")
        if tx is not None:
            score -= _clamp((tx - lim.tx_temp_warn) / (lim.tx_temp - lim.tx_temp_warn)) * 0.16
        run = g("runaway")
        if run is not None:
            score -= _clamp(run / lim.runaway) * 0.24
        ct = g("cell_temp")
        if ct is not None:
            score -= _clamp((ct - 42.0) / (lim.cell_temp - 42.0)) * 0.12
        soh = g("soh")
        if soh is not None:
            score -= _clamp((lim.soh_min + 10 - soh) / 16.0) * 0.10
        ins = g("insulation")
        if ins is not None:
            score -= _clamp((lim.insulation_min * 3 - ins) / (lim.insulation_min * 3)) * 0.08
        return _clamp(score)
