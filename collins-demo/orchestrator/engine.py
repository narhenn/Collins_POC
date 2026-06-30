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

DOMAINS = {
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
    def __init__(self, tenant: str, domain: str, name: str):
        cfg = DOMAINS[domain]
        self.tenant, self.domain, self.name = tenant, domain, name
        self.cfg = cfg
        self.physics = cfg["physics"]()
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
                    self.state.fault = "none"; self.state.fault_severity = 0.0
                    # recover EDM seeded degradation so "clear" visibly heals it
                    for attr, val in (("filter_clog", 0.0), ("resin_depletion", 0.0),
                                      ("guide_wear", 0.0), ("chiller_health", 1.0), ("debris", 0.05)):
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


def _status_for(domain: str, sig: str, v) -> str:
    if v is None:
        return "unknown"
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

    def build(self, domain: str, name: str) -> dict:
        if domain not in DOMAINS:
            domain = "edm-machine"
        tenant = _slug(name or DOMAINS[domain]["label"])
        with self._lock:
            self._twins[tenant] = LiveTwin(tenant, domain, name or DOMAINS[domain]["label"])
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
