"""
engine.py — the in-process digital-twin engine for the Collins demo.

The demo used to need the whole NextXR backend + Neo4j (Docker) just to run the
live twins. That made the demo fragile (Docker crashes = no demo). This module
runs the SAME physics + 3-tier behaviour rules + prediction engine *in-process*,
imported directly from nextxr-ontology — so the orchestrator alone can serve the
live Wire-EDM and turbine twins with NO database and NO Docker.

It manages per-tenant twins on a 1 Hz ticker and exposes exactly what the
orchestrator's nextxr.py client needs: build / state / diagnostics / predict /
project / simulate. Findings are produced by the real behaviour registry and
kept in memory (no graph persistence — which the demo UI never reads anyway).
"""
from __future__ import annotations

import copy
import logging
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("orchestrator.engine")

# Make nextxr-ontology importable (physics / behaviours / predict are pure-Python).
_ROOT = Path(__file__).resolve().parents[2]            # repo root
_ONTO = _ROOT / "nextxr-ontology"
for _p in (str(_ONTO), str(_ONTO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from behaviors.registry import TelemetrySample            # noqa: E402

# ── EDM domain wiring ────────────────────────────────────────────────
from edm.physics import EDMPhysics, SIGNALS as EDM_SIG, UNITS as EDM_UNITS, redlines as EDM_RED  # noqa: E402
from edm.predict import component_health as edm_ch, predict as edm_predict  # noqa: E402
from behaviors.edm import build_edm_registry             # noqa: E402

# ── Turbine domain wiring ────────────────────────────────────────────
from turbine.physics import TurbinePhysics, SIGNALS as TRB_SIG, UNITS as TRB_UNITS, redlines as TRB_RED  # noqa: E402
from turbine.predict import component_health as trb_ch, predict as trb_predict  # noqa: E402
from turbine.ingest import build_turbine_registry         # noqa: E402

# ── Fleet / tram-network domain wiring ───────────────────────────────
from fleet.physics import FleetPhysics, SIGNALS as FLT_SIG, UNITS as FLT_UNITS, redlines as FLT_RED  # noqa: E402
from fleet.predict import component_health as flt_ch, predict as flt_predict  # noqa: E402
from behaviors.fleet import build_fleet_registry           # noqa: E402

# ── EV / GoalCert energy-site domain wiring ──────────────────────────
from ev.physics import EVPhysics, SIGNALS as EV_SIG, UNITS as EV_UNITS, redlines as EV_RED  # noqa: E402
from ev.predict import component_health as ev_ch, predict as ev_predict  # noqa: E402
from behaviors.ev import build_ev_registry                 # noqa: E402

# ── Hospital-campus domain wiring ────────────────────────────────────
from hospital.physics import HospitalCampusPhysics, SIGNALS as HSP_SIG, UNITS as HSP_UNITS  # noqa: E402
from hospital import SENSORS as HSP_SENSORS, SUBSYSTEMS as HSP_SUBSYS, CHECKS as HSP_CHECKS  # noqa: E402
from hospital.predict import component_health as hsp_ch, predict as hsp_predict  # noqa: E402
from behaviors.hospital import build_hospital_registry     # noqa: E402


def _local(sig: str) -> str:
    return sig.split("#")[-1].split(":")[-1]


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name or "twin").strip().lower()).strip("-") or "twin"
    return f"{base[:32]}-{int(time.time() * 1000) % 100000}"


# Per-domain display metadata + status thresholds for the diagnostics surface.
EDM_SENSORS = {
    EDM_SIG["gap_v"]: ("Gap Voltage", "V"), EDM_SIG["peak_i"]: ("Peak Current", "A"),
    EDM_SIG["ton"]: ("Pulse On-Time", "us"), EDM_SIG["toff"]: ("Pulse Off-Time", "us"),
    EDM_SIG["spark_freq"]: ("Spark Frequency", "kHz"), EDM_SIG["energy"]: ("Discharge Energy", "mJ"),
    EDM_SIG["wire_tension"]: ("Wire Tension", "N"), EDM_SIG["wire_feed"]: ("Wire Feed Rate", "m/min"),
    EDM_SIG["wire_wear"]: ("Wire Wear", "%"), EDM_SIG["cut_speed"]: ("Cutting Speed", "mm2/min"),
    EDM_SIG["die_flow"]: ("Dielectric Flow", "L/min"), EDM_SIG["die_press"]: ("Dielectric Pressure", "bar"),
    EDM_SIG["die_temp"]: ("Dielectric Temperature", "C"), EDM_SIG["die_cond"]: ("Dielectric Conductivity", "uS/cm"),
    EDM_SIG["short_rate"]: ("Short-Circuit Rate", "%"), EDM_SIG["spark_gap"]: ("Spark Gap", "um"),
    EDM_SIG["ra"]: ("Surface Finish Ra", "um"), EDM_SIG["break_risk"]: ("Wire-Break Risk", "%"),
}
TRB_SENSORS = {
    TRB_SIG["egt"]: ("Exhaust Gas Temp", "C"), TRB_SIG["n1"]: ("Shaft Speed N1", "RPM"),
    TRB_SIG["n2"]: ("Shaft Speed N2", "RPM"), TRB_SIG["fuel"]: ("Fuel Flow", "kg/h"),
    TRB_SIG["vib"]: ("Vibration", "g"), TRB_SIG["epr"]: ("EPR", ""),
    TRB_SIG["oil_temp"]: ("Oil Temperature", "C"), TRB_SIG["oil_press"]: ("Oil Pressure", "PSI"),
}

FLT_SENSORS = {
    FLT_SIG["otp"]: ("On-Time Performance", "%"), FLT_SIG["headway"]: ("Headway Adherence", "%"),
    FLT_SIG["avg_speed"]: ("Network Speed", "km/h"), FLT_SIG["fleet_avail"]: ("Fleet Availability", "%"),
    FLT_SIG["in_service"]: ("Trams In Service", ""), FLT_SIG["pax_load"]: ("Passenger Load", "%"),
    FLT_SIG["dwell"]: ("Avg Dwell Time", "s"), FLT_SIG["energy"]: ("Traction Power", "MW"),
    FLT_SIG["regen"]: ("Regen Share", "%"), FLT_SIG["ohl_v"]: ("Overhead Voltage", "V"),
    FLT_SIG["sub_load"]: ("Substation Load", "%"), FLT_SIG["track_temp"]: ("Rail Temperature", "C"),
    FLT_SIG["switch_faults"]: ("Switch Faults", ""), FLT_SIG["signal_faults"]: ("Signal Faults", ""),
    FLT_SIG["door_faults"]: ("Door Faults", ""), FLT_SIG["brake_wear"]: ("Brake Wear", "%"),
    FLT_SIG["panto_wear"]: ("Pantograph Wear", "%"), FLT_SIG["traction_temp"]: ("Traction Motor Temp", "C"),
    FLT_SIG["vib"]: ("Bogie Vibration", "g"), FLT_SIG["delay"]: ("Network Delay", "min"),
    FLT_SIG["incidents"]: ("Active Incidents", ""), FLT_SIG["hvac_load"]: ("HVAC Load", "%"),
}

EV_SENSORS = {
    EV_SIG["uptime"]: ("Network Uptime", "%"), EV_SIG["utilization"]: ("Charger Utilisation", "%"),
    EV_SIG["sessions"]: ("Active Sessions", ""), EV_SIG["faulted"]: ("Faulted Chargers", ""),
    EV_SIG["ocpp"]: ("OCPP Heartbeat", "ms"), EV_SIG["queue"]: ("Queue Wait", "min"),
    EV_SIG["power"]: ("Delivered Power", "kW"), EV_SIG["grid_load"]: ("Grid Load", "%"),
    EV_SIG["headroom"]: ("Grid Headroom", "%"), EV_SIG["peak"]: ("Site Demand", "kW"),
    EV_SIG["tx_temp"]: ("Transformer Temp", "C"), EV_SIG["bess_soc"]: ("BESS Charge", "%"),
    EV_SIG["bess_power"]: ("BESS Power", "kW"), EV_SIG["solar"]: ("Solar Output", "kW"),
    EV_SIG["self_use"]: ("Solar Self-Use", "%"), EV_SIG["v2g"]: ("V2G Available", "kWh"),
    EV_SIG["soc"]: ("Fleet Avg SoC", "%"), EV_SIG["soh"]: ("Fleet Avg SoH", "%"),
    EV_SIG["cell_temp"]: ("Cell Temp Max", "C"), EV_SIG["imbalance"]: ("Cell Imbalance", "mV"),
    EV_SIG["coolant"]: ("Coolant Temp", "C"), EV_SIG["insulation"]: ("HV Insulation", "kOhm"),
    EV_SIG["runaway"]: ("Thermal Runaway Risk", "%"),
}

DOMAINS = {
    "ev-network": {
        "label": "GoalCert Energy Site", "control": "demand",
        "physics": EVPhysics, "ch": ev_ch, "predict": ev_predict,
        "registry": build_ev_registry, "sig": EV_SIG, "units": EV_UNITS,
        "sensors": EV_SENSORS,
        "subsys": [("charger", "Charging Network (OCPP)"), ("battery", "Battery Health"),
                   ("grid", "Grid & EMS"), ("energy", "Solar & BESS"),
                   ("thermal", "Thermal Management")],
        "checks": {
            EV_SIG["tx_temp"]: (EV_RED.tx_temp, "above"),
            EV_SIG["grid_load"]: (EV_RED.grid_load, "above"),
            EV_SIG["runaway"]: (EV_RED.runaway, "above"),
            EV_SIG["cell_temp"]: (EV_RED.cell_temp, "above"),
            EV_SIG["imbalance"]: (EV_RED.imbalance, "above"),
            EV_SIG["headroom"]: (EV_RED.headroom_min, "below"),
            EV_SIG["uptime"]: (EV_RED.uptime_min, "below"),
            EV_SIG["faulted"]: (EV_RED.faulted_max, "above"),
            EV_SIG["insulation"]: (EV_RED.insulation_min, "below"),
            EV_SIG["soh"]: (EV_RED.soh_min, "below"),
        },
    },
    "edm-machine": {
        "label": "Wire EDM Machine", "control": "intensity",
        "physics": EDMPhysics, "ch": edm_ch, "predict": edm_predict,
        "registry": build_edm_registry, "sig": EDM_SIG, "units": EDM_UNITS,
        "sensors": EDM_SENSORS,
        "subsys": [("generator", "Discharge Generator"), ("dielectric", "Dielectric & Flushing System"),
                   ("wire_system", "Wire Transport System"), ("guides_axes", "Guides & Axes")],
    },
    "turbine-engine": {
        "label": "Gas Turbine Engine", "control": "throttle",
        "physics": TurbinePhysics, "ch": trb_ch, "predict": trb_predict,
        "registry": build_turbine_registry, "sig": TRB_SIG, "units": TRB_UNITS,
        "sensors": TRB_SENSORS,
        "subsys": [("compressor", "Compressor"), ("combustor", "Combustor"),
                   ("turbine", "Turbine"), ("bearings", "Rotor & Bearings"),
                   ("lubrication", "Lubrication System")],
    },
    "hospital": {
        "label": "St. Vera Hospital", "control": "patient_load",
        "physics": HospitalCampusPhysics, "ch": hsp_ch, "predict": hsp_predict,
        "registry": build_hospital_registry, "sig": HSP_SIG, "units": HSP_UNITS,
        "sensors": HSP_SENSORS,
        "subsys": HSP_SUBSYS,
        "checks": HSP_CHECKS,
    },
    "tram-network": {
        "label": "Tram Fleet Network", "control": "service_level",
        "physics": FleetPhysics, "ch": flt_ch, "predict": flt_predict,
        "registry": build_fleet_registry, "sig": FLT_SIG, "units": FLT_UNITS,
        "sensors": FLT_SENSORS,
        "subsys": [("rolling_stock", "Rolling Stock"), ("power", "Traction Power"),
                   ("track", "Track & Points"), ("signalling", "Signalling & Control"),
                   ("operations", "Operations & Service")],
        # sensor status thresholds for the diagnostics surface
        "checks": {
            FLT_SIG["otp"]: (FLT_RED.otp_min, "below"),
            FLT_SIG["headway"]: (FLT_RED.headway_min, "below"),
            FLT_SIG["ohl_v"]: (FLT_RED.ohl_v_min, "below"),
            FLT_SIG["sub_load"]: (FLT_RED.sub_load_max, "above"),
            FLT_SIG["track_temp"]: (FLT_RED.track_temp_max, "above"),
            FLT_SIG["vib"]: (FLT_RED.vib_max, "above"),
            FLT_SIG["brake_wear"]: (FLT_RED.brake_wear_max, "above"),
            FLT_SIG["panto_wear"]: (FLT_RED.panto_wear_max, "above"),
            FLT_SIG["door_faults"]: (FLT_RED.door_faults_max, "above"),
            FLT_SIG["signal_faults"]: (FLT_RED.signal_faults_max, "above"),
            FLT_SIG["fleet_avail"]: (FLT_RED.fleet_avail_min, "below"),
            FLT_SIG["delay"]: (FLT_RED.delay_max, "above"),
        },
    },
}


class _Query:
    """Minimal read-only query the behaviour rules expect — exposes the latest
    frame's co-located properties (local names) for the Tier-A residual rules."""
    def __init__(self, props): self._p = props
    def get_node(self, t, n): return dict(self._p)
    def get_property(self, t, n, k, default=None): return self._p.get(k, default)
    def list_by_label(self, t, l, limit=100): return []
    def get_findings(self, t, e=None): return []


class LiveTwin:
    def __init__(self, tenant: str, domain: str, name: str, options: dict | None = None):
        cfg = DOMAINS[domain]
        self.tenant, self.domain, self.name = tenant, domain, name
        self.cfg = cfg
        # options are domain-specific physics kwargs — e.g. the fleet domain
        # takes {"network": <spec dict|id>} so ANY fed-in network becomes a twin.
        self.physics = cfg["physics"](**(options or {}))
        self.state = self.physics.init_state()
        self.registry = cfg["registry"]()
        self.latest: dict = {}
        self.findings: list = []
        self.frames = 0
        self.live = True
        self.lock = threading.Lock()
        # prime a few frames so the dashboard opens with real numbers
        for _ in range(3):
            self._step(dt=1.0)

    # ── control input ──
    def _set_control(self, v: float):
        setattr(self.state, self.cfg["control"], float(v))

    def simulate(self, throttle=None, fault=None, severity: float = 0.6, dt: float = 1.0) -> dict:
        with self.lock:
            if throttle is not None:
                self._set_control(throttle)
            if fault is not None:
                if fault == "none":
                    # A domain that knows how to heal itself does it properly
                    # (hospital resets AHU capacity, gas reserve, mains/UPS…);
                    # otherwise fall back to clearing the known EDM/EV seeds.
                    clear = getattr(self.physics, "clear", None)
                    if callable(clear):
                        clear(self.state)
                    else:
                        self.state.fault = "none"; self.state.fault_severity = 0.0
                        # recover seeded degradation so "clear" visibly heals the twin
                        # (EDM + EV fault seeds; permanent aging like SoH is left intact)
                        for attr, val in (("filter_clog", 0.0), ("resin_depletion", 0.0),
                                          ("guide_wear", 0.0), ("chiller_health", 1.0), ("debris", 0.05),
                                          ("charger_fault", 0.0), ("n_faulted", 0.0), ("insul_deg", 0.0),
                                          ("solar_derate", 0.0), ("v2g_loss", 0.0), ("runaway_seed", 0.0)):
                            if hasattr(self.state, attr):
                                setattr(self.state, attr, val)
                else:
                    self.physics.inject(self.state, fault, severity)
            return self._step(dt=dt)

    def _step(self, dt: float = 1.0) -> dict:
        frame = self.physics.forward(self.state, dt=dt)
        self.latest = frame
        self.frames += 1
        props = {_local(k): v for k, v in frame.items()}
        q = _Query(props)
        ts = datetime.now(timezone.utc)
        new = []
        for sig, val in frame.items():
            s = TelemetrySample(signal=sig, entity_id=self.tenant, value=float(val),
                                unit=self.cfg["units"].get(sig, ""), timestamp=ts, tenant_id=self.tenant)
            try:
                for f in self.registry.evaluate(s, q):
                    new.append({"displayName": f.message[:70], "severity": f.severity,
                                "message": f.message, "behaviorId": f.behavior_id, "signal": sig})
            except Exception:  # noqa: BLE001
                pass
        if new:
            self.findings = (new + self.findings)[:12]
        return frame

    # ── read surfaces (match the NextXR shapes the orchestrator expects) ──
    def state_dict(self) -> dict:
        with self.lock:
            frame = dict(self.latest)
            findings = list(self.findings)
        health = self.physics.health_index(frame)
        residuals = self.physics.residuals(frame)
        return {"tenant": self.tenant, "domain": self.domain, "entity_id": self.tenant,
                "frames": self.frames, "health": round(health, 3), "latest": frame,
                "residuals": {k: round(v, 2) for k, v in residuals.items()},
                "findings": findings,
                "incidents": [f for f in findings if f["severity"] == "critical"][:3]}

    def diagnostics(self) -> dict:
        with self.lock:
            frame = dict(self.latest); findings = list(self.findings)
        ch = self.cfg["ch"](self.state, frame, self.physics)
        components = [{"name": label, "type": "subsystem",
                       **ch.get(key, {"health": None, "status": "unknown"})}
                      for key, label in self.cfg["subsys"]]
        sensors = [{"name": lbl, "type": "sensor", "signal": sig, "value": frame.get(sig), "unit": unit,
                    "status": _status_for(self.domain, sig, frame.get(sig))}
                   for sig, (lbl, unit) in self.cfg["sensors"].items()]
        machine = {"id": self.tenant, "name": self.name, **ch.get("overall", {})}
        return {"tenant": self.tenant, "domain": self.domain, "engine": machine, "machine": machine,
                "overall_health": ch.get("overall", {}).get("health"),
                "components": components, "sensors": sensors, "latest": frame, "findings": findings,
                "incidents": []}

    def predict_forward(self, horizon_min: float = 120.0, points: int = 120) -> dict:
        with self.lock:
            st = copy.deepcopy(self.state)
        return self.cfg["predict"](st, horizon_min=horizon_min, points=points, physics=self.physics)

    def project(self, fault=None, severity=0.85, control=None, horizon_min=120.0, points=120) -> dict:
        with self.lock:
            st = copy.deepcopy(self.state)
        if control is not None:
            setattr(st, self.cfg["control"], float(control))
        if fault and fault != "none":
            self.physics.inject(st, fault, float(severity))
        return self.cfg["predict"](st, horizon_min=horizon_min, points=points, physics=self.physics)

    def network(self) -> dict | None:
        """Live 'network' payload for domains that publish one — the fleet map
        (geometry + vehicles + per-route status) or the hospital campus's
        clinical views (bed board, OR schedule, patient flow, infection map,
        medical gas, equipment roster). None for domains without one."""
        if not hasattr(self.physics, "network_state"):
            return None
        with self.lock:
            payload = self.physics.network_state(self.state)
            frame = dict(self.latest)
        payload["latest"] = frame
        # Route/vehicle geometry is fleet-specific — domains whose views are
        # self-describing (hospital) simply have no static geometry to ship.
        net = getattr(self.physics, "net", None)
        if not net:
            return payload
        # ship the (static) geometry once per call — the frontend caches it
        payload["geometry"] = {
            "nodes": net["nodes"], "routes": [
                {k: r[k] for k in ("id", "name", "color", "path", "points",
                                   "length_km", "via", "loop") if k in r}
                for r in net["routes"]],
            "depots": net.get("depots", []),
            "substations": net.get("substations", []),
            "fleet": net.get("fleet", []),
            "route_km": net.get("route_km"),
            "fleet_size": net.get("fleet_size"),
        }
        return payload


def _status_for(domain: str, sig: str, v) -> str:
    if v is None:
        return "unknown"
    # Domains can declare their thresholds in DOMAINS[domain]["checks"];
    # EDM/turbine keep their original hardcoded maps.
    checks = DOMAINS.get(domain, {}).get("checks")
    if checks is None:
        red = EDM_RED if domain == "edm-machine" else TRB_RED
        s = EDM_SIG if domain == "edm-machine" else TRB_SIG
        if domain == "edm-machine":
            checks = {s["short_rate"]: (red.short_rate, "above"), s["break_risk"]: (red.break_risk, "above"),
                      s["die_temp"]: (red.die_temp, "above"), s["die_cond"]: (red.die_cond, "above"),
                      s["die_press"]: (red.die_press_min, "below"), s["wire_tension"]: (red.wire_tension_min, "below"),
                      s["gap_v"]: (red.gap_v_min, "below")}
        else:
            checks = {s["egt"]: (red.egt, "above"), s["oil_temp"]: (red.oil_temp, "above"),
                      s["oil_press"]: (red.oil_press_min, "below"), s["vib"]: (red.vib, "above")}
    if sig in checks:
        lim, d = checks[sig]
        if d == "above":
            return "critical" if v >= lim else "warning" if v >= lim * 0.9 else "ok"
        return "critical" if v <= lim else "warning" if v <= lim * 1.1 else "ok"
    return "ok"


class Engine:
    """Process-wide registry of in-memory live twins + a 1 Hz ticker."""
    def __init__(self):
        self._twins: dict[str, LiveTwin] = {}
        self._lock = threading.Lock()
        threading.Thread(target=self._tick, daemon=True).start()

    def _tick(self):
        while True:
            time.sleep(1.0)
            with self._lock:
                twins = list(self._twins.values())
            for t in twins:
                if t.live:
                    try: t.simulate(dt=2.0)
                    except Exception: pass  # noqa: BLE001 — never kill the ticker

    def build(self, domain: str, name: str, options: dict | None = None) -> dict:
        if domain not in DOMAINS:
            domain = "edm-machine"
        tenant = _slug(name or DOMAINS[domain]["label"])
        with self._lock:
            self._twins[tenant] = LiveTwin(tenant, domain, name or DOMAINS[domain]["label"],
                                           options=options)
        return {"tenant": tenant, "domain": domain,
                "machine": {"id": tenant, "name": name or DOMAINS[domain]["label"]}, "assets": []}

    def twin(self, tenant: str) -> LiveTwin | None:
        with self._lock:
            return self._twins.get(tenant)


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine()
    return _engine
