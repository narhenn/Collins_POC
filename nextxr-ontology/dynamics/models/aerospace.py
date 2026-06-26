"""
aerospace.py — generative models for aerospace MRO equipment.

Coupling (all via the generic engine, no hardcoded wiring):
  TurbineTestRig --testsMRO--> TurbineTestCell (zone)
    * Test rig dumps heat into the cell (thermal coupling via zone model)
    * Monitors EGT, shaft speed N1, fuel flow, vibration
  HydraulicActuator sits in a Room/Zone
    * Monitors system pressure, flow, actuator position

Engineering bases:
  * Turbine EGT: simplified gas-turbine thermodynamic model. EGT rises with
    fuel flow and falls with airflow. Condition index (1.0=new, 0.0=worn)
    models compressor/turbine degradation (blade erosion, coking).
  * Shaft speed N1: PID-like follower of setpoint, perturbed by bearing wear.
  * Hydraulic: pressure = supply - losses. Seal wear → internal leakage →
    pressure drop under load.
"""

from __future__ import annotations

import math
from dynamics.model import DynamicsModel, EntityState, EntityContext

AERO = "https://ontology.nextxr.io/v3/aero#"
CFP  = "https://ontology.nextxr.io/v3/cfp#"

SIG_EGT       = AERO + "exhaustGasTemp"
SIG_N1        = AERO + "shaftSpeedN1"
SIG_FUEL      = AERO + "fuelFlow"
SIG_VIB       = AERO + "vibrationG"
SIG_HYD_PRESS = AERO + "hydraulicPressure"
SIG_HYD_FLOW  = AERO + "flowRate"
SIG_HYD_POS   = AERO + "actuatorPosition"
SIG_PWR       = CFP  + "activePower"
SIG_TEMP      = CFP  + "temperature"


class TurbineTestCellModel(DynamicsModel):
    """Simplified gas-turbine test rig model.

    EGT tracks a nominal value modulated by condition index (fouling/erosion
    lowers turbine efficiency → EGT rises). N1 follows a demand setpoint with
    bearing-wear-driven oscillation. Fuel flow is proportional to power output.
    Vibration correlates with bearing wear and N1 speed.
    """
    archetype = "TurbineTestRig"
    models = [AERO + "TurbineTestRig"]
    produces = [SIG_EGT, SIG_N1, SIG_FUEL, SIG_VIB, SIG_PWR]
    consumes = ["THERMAL zone (ambient)"]

    def init_state(self, ctx):
        return EntityState(
            status="running",
            internal={
                "condition": ctx.fnum("conditionIndex", 1.0),
                "bearing_wear": 0.0,       # 0=new, 1=failed
                "run_hours": 0.0,
                "n1_target": ctx.fnum("nominalN1", 5200.0),
            },
            signals={
                SIG_EGT: ctx.fnum("nominalEGT", 650.0),
                SIG_N1:  ctx.fnum("nominalN1", 5200.0),
                SIG_FUEL: ctx.fnum("fuelFlowKgH", 800.0),
                SIG_VIB: 0.3,
            },
        )

    def step(self, ctx, state):
        dt_h = ctx.dt / 3600.0
        cond = state.internal["condition"]
        wear = state.internal["bearing_wear"]

        # condition degrades slowly (turbine blade erosion, nozzle coking)
        cond_rate = ctx.fnum("conditionDegradePerHour", 0.001)
        cond = max(0.0, cond - cond_rate * dt_h)
        state.internal["condition"] = cond

        # bearing wear accumulates with run time
        wear_rate = ctx.fnum("wearPerHour", 0.0005)
        wear = min(1.0, wear + wear_rate * dt_h)
        state.internal["bearing_wear"] = wear

        state.internal["run_hours"] += dt_h

        # EGT: nominal + degradation offset + noise
        nom_egt = ctx.fnum("nominalEGT", 650.0)
        max_egt = ctx.fnum("maxEGT", 780.0)
        # as condition drops from 1→0, EGT rises with accelerating curve
        # (blade erosion compounds — slow at first, then accelerating)
        deg_offset = (1.0 - cond ** 2) * (max_egt - nom_egt)
        egt = nom_egt + deg_offset + ctx.rng.gauss(0, 3.0)

        # N1 shaft speed: follows target with bearing-friction droop
        n1_target = state.internal["n1_target"]
        n1_noise = ctx.rng.gauss(0, 5.0)
        # bearing wear increases friction → slight N1 droop (FADEC compensates
        # partially but not fully at high wear levels)
        n1_droop = wear * 40.0  # up to 40 RPM droop at full wear
        n1 = n1_target - n1_droop + n1_noise

        # fuel flow proportional to power demand, increases with degradation
        nom_fuel = ctx.fnum("fuelFlowKgH", 800.0)
        fuel = nom_fuel * (1.0 + 0.15 * (1.0 - cond)) + ctx.rng.gauss(0, 5.0)

        # vibration: baseline + bearing wear contribution
        vib_base = 0.3
        vib = vib_base + wear * 2.5 + ctx.rng.gauss(0, 0.05)
        vib = max(0.0, vib)

        # electrical power for test rig systems
        idle_kw = ctx.fnum("idlePowerKW", 50.0)
        max_kw = ctx.fnum("maxPowerKW", 200.0)
        pwr = idle_kw + (max_kw - idle_kw) * 0.7 + ctx.rng.gauss(0, 2.0)

        # heat dump to zone — the test cell absorbs engine waste heat.
        # SpaceThermal reads this via ctx.contained signals as internal heat gain.
        heat_kw = fuel * 0.7  # ~70% of fuel energy becomes waste heat (rest is thrust)

        # status: degrade on high EGT or high vibration
        if egt > max_egt * 0.95 or vib > 2.0:
            state.status = "fault"
        elif egt > nom_egt + 50 or vib > 1.2:
            state.status = "degraded"
        else:
            state.status = "running"

        state.signals = {
            SIG_EGT:  round(egt, 1),
            SIG_N1:   round(n1, 0),
            SIG_FUEL: round(fuel, 1),
            SIG_VIB:  round(vib, 3),
            SIG_PWR:  round(pwr, 2),
            SIG_TEMP: round(25.0 + heat_kw * 0.01, 1),  # heat contribution to zone
        }
        return state


class HydraulicActuatorModel(DynamicsModel):
    """Hydraulic test rig / flight-control actuator model.

    Pressure tracks nominal with seal-wear-driven internal leakage.
    As seals degrade, pressure under load drops below the minimum safe
    operating threshold. Flow cycles to simulate actuator test sequences.
    """
    archetype = "HydraulicActuator"
    models = [AERO + "HydraulicActuator"]
    produces = [SIG_HYD_PRESS, SIG_HYD_FLOW, SIG_HYD_POS, SIG_PWR]
    consumes = []

    def init_state(self, ctx):
        return EntityState(
            status="running",
            internal={
                "seal_condition": ctx.fnum("conditionIndex", 1.0),
                "cycle_count": 0,
                "position": 0.0,        # 0.0 to 1.0 (retracted to extended)
                "direction": 1,          # 1=extending, -1=retracting
            },
            signals={
                SIG_HYD_PRESS: ctx.fnum("nominalPressurePSI", 3000.0),
                SIG_HYD_FLOW: 0.0,
                SIG_HYD_POS: 0.0,
            },
        )

    def step(self, ctx, state):
        dt_h = ctx.dt / 3600.0
        seal = state.internal["seal_condition"]

        # seal wear: accelerates with cycle count
        cycles = state.internal["cycle_count"]
        wear_rate = ctx.fnum("sealWearPerHour", 0.0003) * (1.0 + cycles / 10000.0)
        seal = max(0.0, seal - wear_rate * dt_h)
        state.internal["seal_condition"] = seal

        # actuator cycles back and forth
        pos = state.internal["position"]
        direction = state.internal["direction"]
        speed = 0.02  # position units per tick
        pos += direction * speed
        if pos >= 1.0:
            pos = 1.0
            direction = -1
            state.internal["cycle_count"] += 1
        elif pos <= 0.0:
            pos = 0.0
            direction = 1
        state.internal["position"] = pos
        state.internal["direction"] = direction

        # pressure: nominal minus internal leakage (seal degradation)
        nom_press = ctx.fnum("nominalPressurePSI", 3000.0)
        leakage_drop = (1.0 - seal) * 1500.0  # up to 1500 PSI loss at full wear
        load_drop = abs(speed) * 200.0  # load-dependent pressure drop
        pressure = nom_press - leakage_drop - load_drop + ctx.rng.gauss(0, 15.0)
        pressure = max(0.0, pressure)

        # flow: proportional to actuator movement speed
        max_gpm = ctx.fnum("maxFlowGPM", 20.0)
        flow = max_gpm * abs(speed) / 0.05 + ctx.rng.gauss(0, 0.3)
        flow = max(0.0, flow)

        # power: hydraulic pump power
        pwr = 5.0 + flow * 0.3 + ctx.rng.gauss(0, 0.2)

        # status
        min_press = ctx.fnum("minPressurePSI", 2000.0)
        if pressure < min_press * 0.8:
            state.status = "fault"
        elif pressure < min_press:
            state.status = "degraded"
        else:
            state.status = "running"

        state.signals = {
            SIG_HYD_PRESS: round(pressure, 0),
            SIG_HYD_FLOW:  round(flow, 2),
            SIG_HYD_POS:   round(pos, 3),
            SIG_PWR:       round(pwr, 2),
        }
        return state
