"""
ingest.py — sensor ingestion for the turbine twin.

The 3D layer is the turbine's stand-in for a real engine: it streams sensor
frames in, and this service runs each reading through the SAME detection pipeline
the platform uses for generated telemetry — behaviour registry -> findings ->
change log + event bus -> diagnosis -> incident. So everything downstream
(dashboard, agents, scenarios) works unchanged, now driven by real input.

Per tenant we keep:
  * a behaviour FindingsLoop (aerospace + turbine rules)
  * the latest sensor frame + physics health/residuals (for /state)
  * lightweight diagnosis triggering when new findings appear

Co-located values are stamped onto the engine node as properties (local signal
names) so the Tier-A residual behaviours can read fuel/N1/EGT together.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from behaviors.registry import BehaviorRegistry, TelemetrySample
from behaviors.aerospace import (
    EGTPhysicsResidual, SurgeStallResidual, EGTDeviationBaseline,
    ShaftSpeedBaseline, HydraulicPressureLowRule, EGTRedlineRule,
    OilTempOverTempRule, OilPressureLowRule, VibrationHighRule,
)
from behaviors.diagnosis import DiagnosisEngine
from changelog.service import ChangeLog
from graph.writer import GraphWriter
from graph.query import GraphQuery
from feed.simulate import FindingsLoop
from turbine.physics import TurbinePhysics, SIGNALS, UNITS

logger = logging.getLogger("turbine.ingest")


def build_turbine_registry() -> BehaviorRegistry:
    """A registry of exactly the behaviours that watch turbine signals."""
    r = BehaviorRegistry()
    for b in (EGTPhysicsResidual(), SurgeStallResidual(), EGTDeviationBaseline(),
              ShaftSpeedBaseline(), HydraulicPressureLowRule(), EGTRedlineRule(),
              OilTempOverTempRule(), OilPressureLowRule(), VibrationHighRule()):
        try:
            r.register(b)
        except Exception:  # noqa: BLE001 — duplicate id, skip
            pass
    return r


def _local(signal: str) -> str:
    """Node-property name for a signal CURIE/IRI ('aero:exhaustGasTemp' -> 'exhaustGasTemp')."""
    return signal.split("#")[-1].split(":")[-1]


class _TenantTwin:
    """Live ingestion state for one tenant's turbine."""

    def __init__(self, tenant: str, entity_id: str):
        self.tenant = tenant
        self.entity_id = entity_id
        self.changelog = ChangeLog()
        self.writer = GraphWriter(changelog=self.changelog)
        self.query = GraphQuery()
        self.registry = build_turbine_registry()
        self.loop = FindingsLoop(self.registry, self.writer, self.query)
        self.physics = TurbinePhysics()
        self.fwd_state = self.physics.init_state()   # for throttle-driven sim
        self.latest: dict[str, float] = {}      # signal -> value
        self.findings_emitted = 0
        self.frames = 0
        self.last_diag = 0.0
        self.live = True          # auto-advance every tick (live sensor stream)
        self.lock = threading.Lock()

    def simulate(self, throttle: float | None = None, fault: str | None = None,
                 severity: float = 0.6, dt: float = 1.0) -> dict:
        """Forward-sim one frame from a throttle command (+ optional injected
        fault) and ingest it. Lets the 3D layer drive the twin by control input
        when it isn't streaming every raw sensor itself."""
        if throttle is not None:
            self.fwd_state.throttle = float(throttle)
        if fault is not None:
            if fault == "none":
                self.fwd_state.fault = "none"
                self.fwd_state.fault_severity = 0.0
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

            # 1. Stamp co-located latest values on the engine node so Tier-A
            #    residual behaviours can read fuel/N1/EGT together.
            props = {_local(sig): val for sig, val in readings.items()}
            try:
                self.writer.update(tenant_id=self.tenant, node_id=self.entity_id,
                                   actor="sensor-ingest", properties=props)
            except Exception as e:  # noqa: BLE001 — keep ingesting even if a write hiccups
                logger.debug("node stamp failed: %s", e)

            # 2. Route each reading through the behaviour pipeline.
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

        # 3. If something fired, group findings into an incident (throttled).
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
        """Latest ingested readings, or one physics frame if nothing fed yet."""
        if self.latest:
            return dict(self.latest)
        import copy as _copy
        return self.physics.forward(_copy.deepcopy(self.fwd_state), dt=0.0)

    def diagnostics(self) -> dict:
        """Detailed structured snapshot of the whole twin: every component and
        every sensor, with derived health/status — what the diagnosis agent reports on."""
        from turbine.predict import component_health
        from turbine.physics import SIGNALS

        frame = self._current_frame()
        ch = component_health(self.fwd_state, frame, self.physics)
        d, lim = self.physics.d, self.physics.lim

        # signal status thresholds
        def sig_status(sig, v):
            if v is None:
                return "unknown"
            if sig == SIGNALS["egt"]:
                return "critical" if v >= lim.egt else "warning" if v >= 700 else "ok"
            if sig == SIGNALS["oil_temp"]:
                return "critical" if v >= lim.oil_temp else "warning" if v >= 80 else "ok"
            if sig == SIGNALS["oil_press"]:
                return "critical" if v <= lim.oil_press_min else "warning" if v <= 45 else "ok"
            if sig == SIGNALS["vib"]:
                return "critical" if v >= lim.vib else "warning" if v >= 1.5 else "ok"
            if sig in (SIGNALS["n1"], SIGNALS["n2"]):
                cap = lim.n1 if sig == SIGNALS["n1"] else lim.n2
                return "critical" if v >= cap else "ok"
            return "ok"

        # map sensor entity -> the signal it observes (by type + name)
        SENSOR_MAP = {
            "EGTSensor": SIGNALS["egt"],
            "FuelFlowSensor": SIGNALS["fuel"],
            "VibrationProbe": SIGNALS["vib"],
            "OilTempSensor": SIGNALS["oil_temp"],
            "OilPressureSensor": SIGNALS["oil_press"],
        }
        MODULE_MAP = {  # module class -> component_health key
            "CompressorModule": "compressor",
            "CombustorModule": "combustor",
            "TurbineModule": "turbine",
        }

        engine = {"id": self.entity_id, "name": None}
        components, sensors = [], []
        try:
            for n in self.query.list_by_label(self.tenant, "PhysicalAsset", limit=100):
                ct = (n.get("canonicalType") or "").split("#")[-1]
                name = n.get("displayName")
                if ct == "TurbineTestRig":
                    engine = {"id": n.get("id"), "name": name}
                elif ct in MODULE_MAP:
                    key = MODULE_MAP[ct]
                    components.append({"name": name, "type": ct,
                                       **ch.get(key, {"health": None, "status": "unknown"})})
                elif ct == "ShaftSpeedSensor":
                    sig = SIGNALS["n1"] if "N1" in (name or "") else SIGNALS["n2"]
                    v = frame.get(sig)
                    sensors.append({"name": name, "type": ct, "signal": sig,
                                    "value": v, "status": sig_status(sig, v)})
                elif ct in SENSOR_MAP:
                    sig = SENSOR_MAP[ct]
                    v = frame.get(sig)
                    sensors.append({"name": name, "type": ct, "signal": sig,
                                    "value": v, "status": sig_status(sig, v)})
        except Exception as e:  # noqa: BLE001
            logger.debug("diagnostics entity scan: %s", e)

        # derived subsystems not represented as graph entities
        for key, label in (("bearings", "Rotor & Bearings"),
                           ("lubrication", "Lubrication System")):
            components.append({"name": label, "type": "subsystem", **ch.get(key, {})})

        engine.update(ch.get("overall", {}))
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
            "engine": engine,
            "overall_health": ch.get("overall", {}).get("health"),
            "components": components,
            "sensors": sensors,
            "latest": frame,
            "findings": findings,
            "incidents": incidents,
        }

    def predict_forward(self, horizon_min: float = 120.0, points: int = 120) -> dict:
        """Project the present trajectory forward (prediction engine)."""
        from turbine.predict import predict
        return predict(self.fwd_state, horizon_min=horizon_min, points=points,
                       physics=self.physics)

    def project(self, fault: str | None = None, severity: float = 0.85,
                control: float | None = None, horizon_min: float = 120.0,
                points: int = 120) -> dict:
        """Non-destructive what-if: fork the CURRENT live state, apply a
        hypothetical fault (+ throttle), and project forward. `control` is the
        throttle (0..1). The live twin is untouched."""
        from turbine.predict import predict
        import copy as _copy
        state = _copy.deepcopy(self.fwd_state)
        if control is not None:
            state.throttle = float(control)
        if fault and fault != "none":
            self.physics.inject(state, fault, float(severity))
        return predict(state, horizon_min=horizon_min, points=points,
                       physics=self.physics)

    def state(self) -> dict:
        with self.lock:
            latest = dict(self.latest)
        health = self.physics.health_index(latest) if latest else 1.0
        residuals = self.physics.residuals(latest) if latest else {}
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
            "frames": self.frames,
            "findings_emitted": self.findings_emitted,
            "health": round(health, 3),
            "latest": latest,
            "residuals": {k: round(v, 1) for k, v in residuals.items()},
            "findings": findings,
            "incidents": incidents,
        }


class IngestService:
    """Process-wide registry of per-tenant turbine twins."""

    def __init__(self):
        self._twins: dict[str, _TenantTwin] = {}
        self._lock = threading.Lock()
        # Live ticker: advance every live twin once a second so the dashboard
        # receives a continuous sensor stream (the twin standing in for a real
        # engine). dt>1 sim-second per real second gives visible drift.
        self._ticker = threading.Thread(target=self._tick_loop, daemon=True)
        self._ticker.start()

    def _tick_loop(self):
        while True:
            time.sleep(1.0)
            with self._lock:
                twins = list(self._twins.values())
            for t in twins:
                if getattr(t, "live", False):
                    try:
                        t.simulate(dt=2.0)   # keeps current throttle/fault
                    except Exception:  # noqa: BLE001 — never kill the ticker
                        pass

    def _resolve_entity(self, tenant: str, entity_id: str | None) -> str | None:
        if entity_id:
            return entity_id
        # Fall back to the twin's seed asset (the engine).
        try:
            from twins import TwinRegistry
            twin = TwinRegistry().get(tenant)
            if twin and twin.seed_asset_id:
                return twin.seed_asset_id
        except Exception:  # noqa: BLE001
            pass
        # Else first TurbineTestRig in the graph.
        try:
            for n in GraphQuery().list_by_label(tenant, "PhysicalAsset", limit=100):
                if "Turbine" in (n.get("displayName") or ""):
                    return n["id"]
        except Exception:  # noqa: BLE001
            pass
        return None

    def _domain(self, tenant: str) -> str | None:
        """The twin's domain template, if registered (selects the twin class)."""
        try:
            from twins import TwinRegistry
            tw = TwinRegistry().get(tenant)
            return tw.domain if tw else None
        except Exception:  # noqa: BLE001
            return None

    def twin(self, tenant: str, entity_id: str | None = None):
        """Resolve (and lazily build) the live twin for a tenant. The twin class
        is chosen by the tenant's domain: a wire-EDM machine gets an EDMTwin,
        everything else gets the gas-turbine _TenantTwin. Both expose the same
        simulate / ingest / state / diagnostics / predict_forward interface."""
        with self._lock:
            t = self._twins.get(tenant)
            if t is None:
                ent = self._resolve_entity(tenant, entity_id)
                if ent is None:
                    return None
                if self._domain(tenant) == "edm-machine":
                    from edm.ingest import EDMTwin
                    t = EDMTwin(tenant, ent)
                else:
                    t = _TenantTwin(tenant, ent)
                self._twins[tenant] = t
            elif entity_id and entity_id != t.entity_id:
                t.entity_id = entity_id
            return t


_service: IngestService | None = None


def get_service() -> IngestService:
    global _service
    if _service is None:
        _service = IngestService()
    return _service
