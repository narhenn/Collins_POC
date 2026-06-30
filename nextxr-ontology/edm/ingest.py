"""
ingest.py — sensor ingestion for the wire-EDM twin.

Same role as turbine/ingest.py: the 3D / dashboard layer is the machine's
stand-in. It streams telemetry frames in (or drives the twin by a single
"intensity" command), and this service runs each reading through the SAME
detection pipeline the platform uses everywhere — behaviour registry ->
findings -> change log + event bus -> diagnosis -> incident.

EDMTwin exposes the exact interface the shared IngestService and the API
expect (simulate / ingest / state / diagnostics / predict_forward), so the
existing /api/v1/ingest/* routes serve an EDM twin unchanged.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from behaviors.registry import TelemetrySample
from behaviors.edm import build_edm_registry
from behaviors.diagnosis import DiagnosisEngine
from changelog.service import ChangeLog
from graph.writer import GraphWriter
from graph.query import GraphQuery
from feed.simulate import FindingsLoop
from edm.physics import EDMPhysics, SIGNALS, UNITS, redlines
from edm.predict import component_health, predict as _predict

logger = logging.getLogger("edm.ingest")

# Human label + display unit per signal, for the diagnostics sensor list.
_SENSOR_META = {
    SIGNALS["gap_v"]:        ("Gap Voltage", "V"),
    SIGNALS["peak_i"]:       ("Peak Current", "A"),
    SIGNALS["ton"]:          ("Pulse On-Time", "us"),
    SIGNALS["toff"]:         ("Pulse Off-Time", "us"),
    SIGNALS["spark_freq"]:   ("Spark Frequency", "kHz"),
    SIGNALS["energy"]:       ("Discharge Energy", "mJ"),
    SIGNALS["wire_tension"]: ("Wire Tension", "N"),
    SIGNALS["wire_feed"]:    ("Wire Feed Rate", "m/min"),
    SIGNALS["wire_wear"]:    ("Wire Wear", "%"),
    SIGNALS["cut_speed"]:    ("Cutting Speed", "mm2/min"),
    SIGNALS["die_flow"]:     ("Dielectric Flow", "L/min"),
    SIGNALS["die_press"]:    ("Dielectric Pressure", "bar"),
    SIGNALS["die_temp"]:     ("Dielectric Temperature", "C"),
    SIGNALS["die_cond"]:     ("Dielectric Conductivity", "uS/cm"),
    SIGNALS["short_rate"]:   ("Short-Circuit Rate", "%"),
    SIGNALS["spark_gap"]:    ("Spark Gap", "um"),
    SIGNALS["ra"]:           ("Surface Finish Ra", "um"),
    SIGNALS["break_risk"]:   ("Wire-Break Risk", "%"),
}


def _local(signal: str) -> str:
    """Node-property name for a signal CURIE ('edm:gapVoltage' -> 'gapVoltage')."""
    return signal.split("#")[-1].split(":")[-1]


def _sig_status(signal: str, v: float | None) -> str:
    """Per-signal status word from the redlines."""
    if v is None:
        return "unknown"
    lim = redlines
    if signal == SIGNALS["short_rate"]:
        return "critical" if v >= lim.short_rate else "warning" if v >= lim.short_rate * 0.6 else "ok"
    if signal == SIGNALS["break_risk"]:
        return "critical" if v >= lim.break_risk else "warning" if v >= lim.break_risk * 0.6 else "ok"
    if signal == SIGNALS["die_temp"]:
        return "critical" if v >= lim.die_temp else "warning" if v >= lim.die_temp - 3 else "ok"
    if signal == SIGNALS["die_cond"]:
        return "critical" if v >= lim.die_cond else "warning" if v >= lim.die_cond - 4 else "ok"
    if signal == SIGNALS["die_press"]:
        return "critical" if v <= lim.die_press_min else "warning" if v <= lim.die_press_min + 1.5 else "ok"
    if signal == SIGNALS["wire_tension"]:
        return "critical" if v <= lim.wire_tension_min else "warning" if v <= lim.wire_tension_min + 2 else "ok"
    if signal == SIGNALS["gap_v"]:
        return "critical" if v <= lim.gap_v_min else "warning" if v <= lim.gap_v_min + 6 else "ok"
    return "ok"


class EDMTwin:
    """Live ingestion state for one tenant's wire-EDM machine."""

    def __init__(self, tenant: str, entity_id: str):
        self.tenant = tenant
        self.entity_id = entity_id
        self.domain = "edm-machine"
        self.changelog = ChangeLog()
        self.writer = GraphWriter(changelog=self.changelog)
        self.query = GraphQuery()
        self.registry = build_edm_registry()
        self.loop = FindingsLoop(self.registry, self.writer, self.query)
        self.physics = EDMPhysics()
        self.fwd_state = self.physics.init_state()
        self.latest: dict[str, float] = {}
        self.findings_emitted = 0
        self.frames = 0
        self.last_diag = 0.0
        self.live = True
        self.lock = threading.Lock()

    # ── drive by a single control (3D-layer stand-in) ───────────────
    def simulate(self, throttle: float | None = None, fault: str | None = None,
                 severity: float = 0.6, dt: float = 1.0) -> dict:
        """Forward-sim one frame. `throttle` is the programmed discharge
        intensity (0..1) for this machine; `fault` is one of EDMPhysics.FAULTS."""
        if throttle is not None:
            self.fwd_state.intensity = float(throttle)
        if fault is not None:
            if fault == "none":
                # Clear the fault AND recover the seeded degradation back to a
                # healthy machine, so "Healthy (clear)" visibly restores the twin.
                st = self.fwd_state
                st.fault = "none"; st.fault_severity = 0.0
                st.filter_clog = 0.0; st.resin_depletion = 0.0
                st.guide_wear = 0.0; st.chiller_health = 1.0; st.debris = 0.05
            else:
                self.physics.inject(self.fwd_state, fault, severity)
        frame = self.physics.forward(self.fwd_state, dt=dt)
        result = self.ingest(frame)
        return {"frame": frame, **result}

    def ingest(self, readings: dict[str, float], ts: datetime | None = None) -> dict:
        ts = ts or datetime.now(timezone.utc)
        emitted = []
        with self.lock:
            self.latest.update(readings)
            self.frames += 1
            props = {_local(sig): val for sig, val in readings.items()}
            try:
                self.writer.update(tenant_id=self.tenant, node_id=self.entity_id,
                                   actor="sensor-ingest", properties=props)
            except Exception as e:  # noqa: BLE001
                logger.debug("node stamp failed: %s", e)
            for sig, val in readings.items():
                sample = TelemetrySample(
                    signal=sig, entity_id=self.entity_id, value=float(val),
                    unit=UNITS.get(sig, ""), timestamp=ts, tenant_id=self.tenant)
                try:
                    outcomes = self.loop.process(sample)
                    self.findings_emitted += len(outcomes)
                    emitted.extend(outcomes)
                except Exception as e:  # noqa: BLE001
                    logger.debug("behaviour eval failed for %s: %s", sig, e)
        if emitted and (time.time() - self.last_diag) > 3.0:
            self.last_diag = time.time()
            self._run_diagnosis()
        return {"accepted": len(readings), "findings_this_frame": len(emitted)}

    def _run_diagnosis(self):
        try:
            all_f = self.query.get_findings(self.tenant)
            ids = [f["id"] for f in all_f
                   if f.get("id") and not f.get("groupedInto")]
            if ids:
                DiagnosisEngine(self.writer, self.query).analyze(
                    self.tenant, ids, self.entity_id)
        except Exception as e:  # noqa: BLE001
            logger.debug("diagnosis skip: %s", e)

    def _current_frame(self) -> dict:
        if self.latest:
            return dict(self.latest)
        import copy as _copy
        return self.physics.forward(_copy.deepcopy(self.fwd_state), dt=0.0)

    # ── read surfaces ────────────────────────────────────────────────
    def state(self) -> dict:
        with self.lock:
            latest = dict(self.latest)
        if not latest:
            latest = self._current_frame()
        health = self.physics.health_index(latest)
        residuals = self.physics.residuals(latest)
        findings, incidents = [], []
        try:
            findings = self.query.get_findings(self.tenant)[:15]
        except Exception:  # noqa: BLE001
            pass
        try:
            incidents = self.query.list_by_label(self.tenant, "Incident", limit=5)
        except Exception:  # noqa: BLE001
            pass
        return {
            "tenant": self.tenant,
            "entity_id": self.entity_id,
            "domain": self.domain,
            "frames": self.frames,
            "findings_emitted": self.findings_emitted,
            "health": round(health, 3),
            "latest": latest,
            "residuals": {k: round(v, 2) for k, v in residuals.items()},
            "findings": findings,
            "incidents": incidents,
        }

    def diagnostics(self) -> dict:
        """Detailed per-subsystem / per-sensor snapshot of the live twin —
        same shape the turbine twin returns so the agents reuse it unchanged."""
        frame = self._current_frame()
        ch = component_health(self.fwd_state, frame, self.physics)

        # Subsystems (from the physics health model). The graph carries the
        # same modules as entities, but health is derived here.
        SUBSYS = [("generator", "Discharge Generator"),
                  ("dielectric", "Dielectric & Flushing System"),
                  ("wire_system", "Wire Transport System"),
                  ("guides_axes", "Guides & Axes")]
        components = [{"name": label, "type": "subsystem",
                       **ch.get(key, {"health": None, "status": "unknown"})}
                      for key, label in SUBSYS]

        sensors = []
        for sig, (label, unit) in _SENSOR_META.items():
            v = frame.get(sig)
            sensors.append({"name": label, "type": "EDMSensor", "signal": sig,
                            "value": v, "unit": unit, "status": _sig_status(sig, v)})

        machine = {"id": self.entity_id, "name": "Wire EDM Machine",
                   **ch.get("overall", {})}
        findings, incidents = [], []
        try:
            findings = self.query.get_findings(self.tenant)[:15]
        except Exception:  # noqa: BLE001
            pass
        try:
            incidents = self.query.list_by_label(self.tenant, "Incident", limit=5)
        except Exception:  # noqa: BLE001
            pass
        # Try to enrich machine name from the graph.
        try:
            node = self.query.get_node(self.tenant, self.entity_id)
            if node and node.get("displayName"):
                machine["name"] = node["displayName"]
        except Exception:  # noqa: BLE001
            pass

        return {
            "tenant": self.tenant,
            "domain": self.domain,
            "engine": machine,          # keep key name for agent reuse
            "machine": machine,
            "overall_health": ch.get("overall", {}).get("health"),
            "components": components,
            "sensors": sensors,
            "latest": frame,
            "findings": findings,
            "incidents": incidents,
        }

    def predict_forward(self, horizon_min: float = 120.0, points: int = 120) -> dict:
        import copy as _copy
        return _predict(_copy.deepcopy(self.fwd_state), horizon_min=horizon_min,
                        points=points, physics=self.physics)

    def project(self, fault: str | None = None, severity: float = 0.85,
                control: float | None = None, horizon_min: float = 120.0,
                points: int = 120) -> dict:
        """Non-destructive what-if: fork the CURRENT live state, apply a
        hypothetical fault (+ machining intensity), and project forward. The live
        twin is untouched. `control` is the programmed intensity (0..1)."""
        import copy as _copy
        state = _copy.deepcopy(self.fwd_state)
        if control is not None:
            state.intensity = float(control)
        if fault and fault != "none":
            self.physics.inject(state, fault, float(severity))
        return _predict(state, horizon_min=horizon_min, points=points,
                        physics=self.physics)
