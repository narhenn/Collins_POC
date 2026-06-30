"""
claude_client.py — the agentic brain (Claude / Anthropic).

Two jobs:
  1. vision_to_twin_spec(image, description) — read a 2D machine photo + a short
     description and extract a structured digital-twin spec (machine + sensors,
     each mapped to a live NextXR telemetry signal and a 3D hotspot position).
  2. scenario_brief(prompt, assets) — turn a natural-language "what if" into a
     structured scenario brief used to drive the GoalCert simulation engine.

If no ANTHROPIC_API_KEY is set, both fall back to a deterministic turbine stub
so the whole golden path still runs end-to-end for a dry run.
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

from pydantic import BaseModel, Field

from config import config

logger = logging.getLogger("orchestrator.claude")

# NextXR's aerospace-MRO feed emits these signals. Mapping a sensor to one of
# these keys means its 3D hotspot lights up from real live telemetry. Anything
# else still renders, just without a live binding.
KNOWN_SIGNALS = {
    "aero:exhaustGasTemp": ("Exhaust Gas Temp", "°C"),
    "aero:shaftSpeedN1": ("Shaft Speed N1", "RPM"),
    "aero:hydraulicPressure": ("Hydraulic Pressure", "PSI"),
    "aero:avionicsBayTemp": ("Avionics Bay Temp", "°C"),
    "cfp:oilTemperature": ("Oil Temperature", "°C"),
    "cfp:chillerCOP": ("Chiller COP", ""),
    "cfp:upsSoC": ("UPS State of Charge", "%"),
}


# ── Structured twin spec (what the Vision Agent returns) ──────────────

class SensorSpec(BaseModel):
    name: str = Field(description="Human label, e.g. 'Exhaust Gas Temp'")
    signal_key: str = Field(
        description="One of the known NextXR signal keys when applicable "
                    "(aero:exhaustGasTemp, aero:shaftSpeedN1, "
                    "aero:hydraulicPressure, cfp:oilTemperature), else a short "
                    "custom key like 'turbine:bearingVibration'.")
    unit: str = Field(description="Measurement unit, e.g. '°C', 'RPM', 'PSI'")
    position: list[float] = Field(
        description="Approximate [x, y, z] hotspot position on the machine, "
                    "each in -1..1, origin at the machine centre.")
    normal: str = Field(default="", description="Normal operating range, free text.")
    description: str = Field(default="", description="What this sensor monitors.")


class TwinSpec(BaseModel):
    machine_type: str = Field(description="e.g. 'Turbofan turbine test rig'")
    machine_name: str = Field(description="A short asset name, e.g. 'Turbine Rig TR-01'")
    summary: str = Field(description="One-paragraph description of the machine.")
    components: list[str] = Field(default_factory=list,
                                  description="Major sub-components identified.")
    sensors: list[SensorSpec] = Field(description="Sensors mapped onto the machine.")


# ── Deterministic fallback (no API key) ───────────────────────────────

def _turbine_stub() -> TwinSpec:
    return TwinSpec(
        machine_type="Turbofan turbine test rig",
        machine_name="Turbine Rig TR-01",
        summary=("A turbofan engine mounted on an MRO test rig. The fan and "
                 "low-pressure compressor draw air through the inlet; the core "
                 "burns fuel to spin the turbine and exhaust hot gas. Monitored "
                 "for exhaust gas temperature, shaft speed, vibration, and oil "
                 "temperature during ground runs."),
        components=["Inlet / fan", "Compressor", "Combustor", "Turbine",
                    "Exhaust nozzle", "Accessory gearbox"],
        sensors=[
            SensorSpec(name="Exhaust Gas Temp", signal_key="aero:exhaustGasTemp",
                       unit="°C", position=[0.7, 0.1, 0.0],
                       normal="640–710 °C", description="Hot-section health."),
            SensorSpec(name="Shaft Speed N1", signal_key="aero:shaftSpeedN1",
                       unit="RPM", position=[-0.2, 0.0, 0.0],
                       normal="~5200 RPM", description="Low-pressure spool speed."),
            SensorSpec(name="Oil Temperature", signal_key="cfp:oilTemperature",
                       unit="°C", position=[0.1, -0.4, 0.2],
                       normal="< 85 °C", description="Bearing/lube oil temp."),
            SensorSpec(name="Bearing Vibration", signal_key="turbine:bearingVibration",
                       unit="mm/s", position=[0.3, 0.3, -0.2],
                       normal="< 7 mm/s", description="Rotor balance / bearing wear."),
            SensorSpec(name="Hydraulic Pressure", signal_key="aero:hydraulicPressure",
                       unit="PSI", position=[-0.6, -0.3, 0.1],
                       normal="2700–3200 PSI", description="Actuation supply."),
        ],
    )


# ── Anthropic client (lazy) ───────────────────────────────────────────

_client = None


def _anthropic():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _data_uri(image_b64: str, filename: str) -> tuple[str, str]:
    """Return (media_type, raw_base64) from a base64 string or data-URI."""
    if image_b64.startswith("data:"):
        header, _, data = image_b64.partition(",")
        media = header.split(";")[0].removeprefix("data:") or "image/png"
        return media, data
    media = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    return media, image_b64


# ── Public API ────────────────────────────────────────────────────────

def vision_to_twin_spec(image_b64: Optional[str], description: str,
                        filename: str = "machine.png") -> TwinSpec:
    """Claude vision → structured twin spec. Falls back to a turbine stub."""
    if not config.claude_enabled or not image_b64:
        logger.info("vision: using deterministic turbine stub (no key/image)")
        spec = _turbine_stub()
        if description:
            spec.summary = f"{description.strip()} — {spec.summary}"
        return spec

    media_type, data = _data_uri(image_b64, filename)
    signal_hint = ", ".join(KNOWN_SIGNALS.keys())
    system = (
        "You are the Vision Agent for an aerospace MRO digital-twin platform. "
        "Given a photo of a machine and a short description, identify the machine "
        "and the sensors a maintenance team would monitor on it. Map each sensor "
        "to one of these live telemetry signal keys when it fits "
        f"({signal_hint}); otherwise invent a short key like 'turbine:bearingVibration'. "
        "Give each sensor an approximate 3D hotspot position on the machine as "
        "[x,y,z] in -1..1 with the origin at the machine centre.")
    try:
        client = _anthropic()
        resp = client.messages.parse(
            model=config.CLAUDE_MODEL,
            max_tokens=2000,
            system=system,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": media_type, "data": data}},
                    {"type": "text", "text":
                        f"Description from the operator: {description or '(none)'}\n\n"
                        "Extract the machine and its monitored sensors."},
                ],
            }],
            output_format=TwinSpec,
        )
        spec = resp.parsed_output
        if spec is None:
            raise ValueError("no parsed output")
        return spec
    except Exception as e:  # noqa: BLE001 — best-effort, fall back cleanly
        logger.warning("vision parse failed (%s); using turbine stub", e)
        return _turbine_stub()


class ScenarioBrief(BaseModel):
    name: str = Field(description="Short scenario title.")
    fault_summary: str = Field(description="What goes wrong, in one or two sentences.")
    primary_signal: str = Field(description="The signal that deviates, e.g. aero:exhaustGasTemp.")
    severity: str = Field(description="One of: Low, Medium, High, Critical.")
    steps: list[str] = Field(description="3–6 technician repair/verification steps.")
    expected_behavior: str = Field(description="How the machine behaves during the fault.")


def _scenario_stub(prompt: str) -> ScenarioBrief:
    return ScenarioBrief(
        name="Turbine EGT Overtemp During Ground Run",
        fault_summary=("Exhaust gas temperature climbs past the redline during a "
                       "ground run, indicating hot-section distress (possible "
                       "nozzle coking or blade erosion)."),
        primary_signal="aero:exhaustGasTemp",
        severity="Critical",
        steps=["Reduce thrust and stabilise the engine",
               "Borescope the hot section for blade/nozzle damage",
               "Check fuel nozzle spray pattern",
               "Replace affected components per the MRO manual",
               "Re-run and verify EGT returns within limits"],
        expected_behavior=("EGT ramps from ~660 °C to >780 °C over ~10 minutes; "
                           "Tier-B baseline flags the deviation, then a Tier-C "
                           "threshold trips and an incident is raised."),
    )


# ── Build-a-Twin conversational agent ────────────────────────────────

class TwinBuilderReply(BaseModel):
    reply: str = Field(description="The agent's conversational reply to the user.")
    ready: bool = Field(description="True once the user has described the machine "
                                    "and is ready to generate/build the twin.")
    machine_name: str = Field(default="", description="A short asset name if known.")


def build_twin_reply(history: list[dict], message: str) -> TwinBuilderReply:
    """Twin Builder agent: converse to gather what to twin, then signal readiness.
    history is [{role:'user'|'assistant', content:str}]."""
    user_turns = len([h for h in history if h.get("role") == "user"]) + 1

    def _stub() -> TwinBuilderReply:
        m = (message or "").strip()
        if user_turns <= 1:
            return TwinBuilderReply(reply=(
                "Hi! I'm the Twin Builder. I turn a real machine into a live digital "
                "twin. What machine are we twinning — and a few words about it? "
                "(e.g. 'a GE turbofan engine on our MRO test rig')"), ready=False)
        if user_turns == 2:
            return TwinBuilderReply(reply=(
                f"Got it — “{m}”. Now drop a 2D image of the machine below and I'll "
                "reconstruct it in 3D, then build the live twin with its sensors."),
                ready=True, machine_name=(m[:40] or "Turbine Engine"))
        return TwinBuilderReply(reply=(
            "Great — upload the image and hit Build. I'll reconstruct the 3D model "
            "and wire up the live sensors and physics."),
            ready=True, machine_name=(m[:40] or "Turbine Engine"))

    if not config.claude_enabled:
        return _stub()
    try:
        msgs = [{"role": h["role"], "content": h["content"]} for h in history[-8:]]
        msgs.append({"role": "user", "content": message})
        system = (
            "You are the Twin Builder agent for an aerospace MRO digital-twin "
            "platform. Converse warmly and briefly to learn what machine the user "
            "wants to twin (a gas turbine / jet engine for this demo). Once they've "
            "named/described it, set ready=true and tell them to upload a 2D IMAGE of "
            "the machine, then hit Build — you'll reconstruct the 3D model from the "
            "image and wire up live sensors + physics. Image only (no text prompt). "
            "Keep replies to 1-3 sentences.")
        resp = _anthropic().messages.parse(
            model=config.CLAUDE_MODEL, max_tokens=400, system=system,
            messages=msgs, output_format=TwinBuilderReply)
        return resp.parsed_output or _stub()
    except Exception as e:  # noqa: BLE001
        logger.warning("build_twin_reply failed (%s); stub", e)
        return _stub()


# ── Turbine scenario builder (agent authors a runnable what-if) ───────

# The fault catalogue the projection engine understands.
FAULT_CATALOG = {
    "blade_erosion": "Turbine blade erosion — hot-section efficiency loss, EGT climbs to redline.",
    "nozzle_coking": "Fuel-nozzle coking — uneven combustion, local hot streak.",
    "compressor_fouling": "Compressor fouling — reduced airflow, EGT creep.",
    "bearing_wear": "Bearing wear — rising vibration and N1 droop.",
    "oil_starvation": "Oil leak / starvation — oil temp up, oil pressure down.",
    "surge": "Compressor surge / stall — N1 collapse with EGT spike.",
    "sensor_failure": "EGT sensor failure — reading freezes while the engine keeps "
                      "degrading underneath (the twin flies blind).",
}


class AuthoredScenario(BaseModel):
    name: str = Field(description="Short, specific scenario title.")
    fault: str = Field(description="EXACTLY one fault id from the catalogue.")
    severity: float = Field(description="0..1 how aggressive the fault is.")
    throttle: float = Field(description="0..1 engine thrust setting during the run.")
    horizon_min: float = Field(description="Minutes to project forward (10-60).")
    rationale: str = Field(description="Why this fault/params model the request.")
    expected_outcome: str = Field(description="One-sentence prediction of the result.")


def _author_stub(prompt: str) -> AuthoredScenario:
    p = (prompt or "").lower()
    fault = "blade_erosion"
    for fid in FAULT_CATALOG:
        if fid.split("_")[0] in p or fid in p:
            fault = fid
            break
    if "vibrat" in p or "bearing" in p:
        fault = "bearing_wear"
    elif "oil" in p or "leak" in p:
        fault = "oil_starvation"
    elif "sensor" in p or "blind" in p:
        fault = "sensor_failure"
    elif "surge" in p or "stall" in p:
        fault = "surge"
    return AuthoredScenario(
        name=prompt.strip()[:60] or "Hot-section distress",
        fault=fault, severity=0.85, throttle=0.95, horizon_min=30.0,
        rationale=f"Mapped the request to the '{fault}' physics fault.",
        expected_outcome=FAULT_CATALOG.get(fault, ""))


def author_scenario(prompt: str, machine: str, sensors: list[str]) -> AuthoredScenario:
    """Agent: turn a natural-language request into a runnable scenario spec."""
    if not config.claude_enabled:
        return _author_stub(prompt)
    catalog = "\n".join(f"  - {k}: {v}" for k, v in FAULT_CATALOG.items())
    system = (
        "You are the Scenario Builder agent for an aerospace turbine digital twin. "
        "Turn the operator's request into a runnable what-if scenario by choosing "
        "the single best-matching fault from this catalogue and sensible parameters:\n"
        f"{catalog}\n"
        "Pick severity (0..1), throttle (0..1), and horizon_min (10-60) that make "
        "the scenario realistic and likely to reveal the outcome. 'fault' MUST be "
        "one of the catalogue ids exactly.")
    try:
        resp = _anthropic().messages.parse(
            model=config.CLAUDE_MODEL, max_tokens=1200, system=system,
            messages=[{"role": "user", "content":
                f"Machine: {machine}\nSensors: {', '.join(sensors)}\n"
                f"Request: {prompt}"}],
            output_format=AuthoredScenario)
        spec = resp.parsed_output or _author_stub(prompt)
        if spec.fault not in FAULT_CATALOG:
            spec.fault = _author_stub(prompt).fault
        return spec
    except Exception as e:  # noqa: BLE001
        logger.warning("author_scenario failed (%s); stub", e)
        return _author_stub(prompt)


def analyze_outcome(scenario: dict, projection: dict, machine: str) -> str:
    """Agent: plain-English analysis of the projected outcome — what happens, how
    the machine behaves, and what to do to be ready. Stub falls back to a
    deterministic summary from the projection data."""
    o = projection.get("outcome", {})
    events = projection.get("events", [])

    def _stub() -> str:
        bits = []
        sev = o.get("severity", "nominal")
        if o.get("time_to_redline_min") is not None:
            bits.append(f"EGT reaches the {780} C redline in about "
                        f"{o['time_to_redline_min']:.0f} minutes.")
        bits.append(f"Predicted severity: {sev}. "
                    f"Peak EGT {o.get('peak_egt')} C, peak vibration "
                    f"{o.get('peak_vibration')} g, min oil pressure "
                    f"{o.get('min_oil_pressure')} PSI, health bottoms at "
                    f"{o.get('min_health')}.")
        if o.get("blind_spot"):
            bits.append("WARNING: the EGT sensor reading stays frozen, so only the "
                        "physics residual catches the overheat — the crew would "
                        "otherwise be blind to it.")
        if events:
            bits.append("Detections (in order): " +
                        ", ".join(e["behavior_id"] for e in events) + ".")
        acts = o.get("recommended_actions") or []
        if acts:
            bits.append("Recommended actions: " + "; ".join(acts) + ".")
        return " ".join(bits)

    if not config.claude_enabled:
        return _stub()
    try:
        import json as _json
        system = (
            "You are an aerospace MRO reliability engineer. Given a turbine what-if "
            "projection, write a concise, actionable briefing (4-6 sentences): what "
            "happens to the engine, how it behaves over time, the key risk and "
            "time-to-action, and the precautions/maintenance to be ready. Be specific "
            "and grounded in the numbers; no preamble.")
        resp = _anthropic().messages.create(
            model=config.CLAUDE_MODEL, max_tokens=600,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content":
                f"Machine: {machine}\nScenario: {_json.dumps(scenario)}\n"
                f"Outcome: {_json.dumps(o)}\nEvents: {_json.dumps(events)}"}])
        return "".join(b.text for b in resp.content if b.type == "text").strip() or _stub()
    except Exception as e:  # noqa: BLE001
        logger.warning("analyze_outcome failed (%s); stub", e)
        return _stub()


# ── Diagnosis agent (detailed component/sensor report of the live twin) ──

def diagnosis_agent(diagnostics: dict, machine: str) -> str:
    """Diagnose the real-time twin: per-component health, per-sensor status,
    overall condition, likely root cause, and recommended actions."""
    comps = diagnostics.get("components", [])
    sensors = diagnostics.get("sensors", [])
    findings = diagnostics.get("findings", [])
    overall = diagnostics.get("overall_health")

    def _stub() -> str:
        lines = [f"DIAGNOSIS — {machine}",
                 f"Overall health: {round((overall or 0)*100)}%."]
        bad = [c for c in comps if (c.get('health') or 1) < 0.6]
        if bad:
            lines.append("Components needing attention: " +
                         ", ".join(f"{c['name']} ({c['status']}, "
                                   f"{round((c.get('health') or 0)*100)}%)" for c in bad) + ".")
        else:
            lines.append("All components within healthy bounds.")
        alarms = [s for s in sensors if s.get("status") in ("warning", "critical")]
        if alarms:
            lines.append("Sensors out of band: " +
                         ", ".join(f"{s['name']}={s['value']} ({s['status']})" for s in alarms) + ".")
        if findings:
            lines.append("Active findings: " +
                         "; ".join((f.get("message") or "")[:80] for f in findings[:4]) + ".")
        return " ".join(lines)

    if not config.claude_enabled:
        return _stub()
    try:
        import json as _json
        system = (
            "You are an aerospace MRO diagnostic engineer. Given a structured "
            "snapshot of a gas-turbine digital twin (components, sensors, findings), "
            "write a clear diagnosis report: (1) overall condition, (2) a line per "
            "component with its health and what it implies, (3) any sensors out of "
            "band, (4) the most likely root cause, (5) recommended actions. Be "
            "specific and grounded in the numbers. Use short sections, no preamble.")
        resp = _anthropic().messages.create(
            model=config.CLAUDE_MODEL, max_tokens=1000,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content":
                f"Machine: {machine}\nSnapshot: {_json.dumps(diagnostics, default=str)[:6000]}"}])
        return "".join(b.text for b in resp.content if b.type == "text").strip() or _stub()
    except Exception as e:  # noqa: BLE001
        logger.warning("diagnosis_agent failed (%s); stub", e)
        return _stub()


# ── Analysis agent (present + future, combined with the prediction engine) ──

def analysis_agent(diagnostics: dict, prediction: dict, machine: str,
                   horizon_label: str) -> str:
    """Analyse the whole twin now AND project the assessment over the chosen
    horizon using the prediction engine output."""
    overall = diagnostics.get("overall_health")
    rul = prediction.get("rul", [])
    ev = prediction.get("events", [])
    ch_now = prediction.get("component_health_now", {})
    ch_fut = prediction.get("component_health_horizon", {})

    def _stub() -> str:
        lines = [f"ANALYSIS — {machine} (now + next {horizon_label})",
                 f"Present overall health: {round((overall or 0)*100)}%."]
        crossings = [r for r in rul if r.get("within_horizon")]
        if crossings:
            for r in crossings:
                lines.append(f"Projected to reach {r['mode']} in "
                             f"~{r['time_to_limit_min']:.0f} min.")
        else:
            lines.append(f"No operating limit is projected to be crossed within "
                         f"the next {horizon_label}.")
        # component deltas
        deltas = []
        for k in ("compressor", "turbine", "bearings", "lubrication"):
            a = (ch_now.get(k, {}) or {}).get("health")
            b = (ch_fut.get(k, {}) or {}).get("health")
            if a is not None and b is not None and (a - b) > 0.05:
                deltas.append(f"{k} {round(a*100)}%→{round(b*100)}%")
        if deltas:
            lines.append("Degrading over the horizon: " + ", ".join(deltas) + ".")
        if ev:
            lines.append("Predicted detections: " +
                         ", ".join(e["behavior_id"] for e in ev) + ".")
        return " ".join(lines)

    if not config.claude_enabled:
        return _stub()
    try:
        import json as _json
        system = (
            "You are an aerospace MRO reliability analyst. You are given (a) a "
            "present snapshot of a turbine twin and (b) a physics PREDICTION of how "
            f"it evolves over the next {horizon_label}. Write an analysis covering: "
            "the present state of each sensor/component, how they are TRENDING, the "
            "predicted remaining-useful-life / time-to-limit, and the precautions to "
            "take to be ready. Be specific and grounded; short sections; no preamble.")
        payload = {"present": diagnostics, "prediction": {
            "horizon_min": prediction.get("horizon_min"),
            "rul": rul, "events": ev,
            "component_health_now": ch_now, "component_health_horizon": ch_fut}}
        resp = _anthropic().messages.create(
            model=config.CLAUDE_MODEL, max_tokens=1100,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content":
                f"Machine: {machine}\n{_json.dumps(payload, default=str)[:7000]}"}])
        return "".join(b.text for b in resp.content if b.type == "text").strip() or _stub()
    except Exception as e:  # noqa: BLE001
        logger.warning("analysis_agent failed (%s); stub", e)
        return _stub()


# ── Real-time narration (the AI co-pilot watching the live sensor stream) ──

def narrate_sensors(state: dict, machine: str, prediction: dict | None = None) -> str:
    """Claude watches the current sensor snapshot and issues a 1-2 sentence
    observation in real-time, like an experienced operations engineer. Works for
    any twin (turbine, wire-EDM, facility…) — it reasons from whatever signals it
    is given, so the same co-pilot narrates every machine from its own telemetry."""
    signals = state.get("latest", state.get("signals", {}))
    findings = state.get("findings", [])
    health = state.get("health", {})
    residuals = state.get("residuals", {})
    rul = (prediction or {}).get("rul", [])
    crossings = [r for r in rul if r.get("within_horizon")]

    def _stub() -> str:
        if findings:
            return f"Active finding: {findings[0].get('message', 'anomaly detected')[:90]}."
        # Generic, domain-neutral fallback from whatever signals exist.
        items = [(k.split(':')[-1], v) for k, v in list(signals.items())[:3]
                 if isinstance(v, (int, float))]
        if items:
            shown = ", ".join(f"{n} {v:.0f}" for n, v in items)
            return f"All readings nominal — {shown}. {machine} running clean."
        return "Waiting for sensor data…"

    if not config.claude_enabled:
        return _stub()
    try:
        import json as _json
        system = (
            f"You are an experienced operations & maintenance engineer monitoring "
            f"a live {machine} on the control console. Given the current sensor "
            "readings, issue ONE concise observation (1-2 sentences, present tense). "
            "Flag anomalies, trends, or quiet-but-concerning patterns and name the "
            "specific signals. Sound experienced and calm — not alarmed unless "
            "readings are truly critical. No preamble, no labels.")
        user = (
            f"Machine: {machine}\n"
            f"Sensors: {_json.dumps(signals, default=str)}\n"
            f"Residuals (measured - expected): {_json.dumps(residuals, default=str)}\n"
            f"Health: {_json.dumps(health, default=str)}\n"
            f"Active findings: {len(findings)}")
        if findings:
            user += f"\nLatest finding: {findings[0].get('message', '')[:120]}"
        if crossings:
            user += f"\nPREDICTION: {_json.dumps(crossings[:2], default=str)}"
        resp = _anthropic().messages.create(
            model=config.CLAUDE_MODEL, max_tokens=200,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in resp.content if b.type == "text").strip() or _stub()
    except Exception as e:
        logger.warning("narrate_sensors failed (%s); stub", e)
        return _stub()


# ── Per-asset AI status (click an asset in the 3D scene → ask the AI) ──

def asset_status(asset: dict, machine: str, domain: str = "") -> str:
    """Detailed, telemetry-grounded status for ONE component/asset the user
    clicked in the 3-D scene. Works for any twin — it reasons from the asset's
    own readings."""
    import json as _json
    name = asset.get("name") or asset.get("id") or "Component"
    atype = asset.get("type") or ""
    metrics = asset.get("metrics") or {}
    status = asset.get("status") or "ok"

    def _stub() -> str:
        sev = {"crit": "CRITICAL", "warn": "WARNING"}.get(status, "HEALTHY")
        mtxt = ", ".join(f"{k} {v}" for k, v in list(metrics.items())[:4]) or "no live readings"
        if status == "crit":
            return (f"{name} — {sev}. Readings: {mtxt}. This component has crossed an "
                    f"operating limit; isolate it and raise a work order before continued use.")
        if status == "warn":
            return (f"{name} — {sev}. Readings: {mtxt}. Drifting out of band; trend it "
                    f"closely and schedule an inspection.")
        return f"{name} — {sev}. Readings: {mtxt}. Operating within normal limits."

    if not config.claude_enabled:
        return _stub()
    try:
        system = (
            f"You are an experienced maintenance engineer for a {machine}. The "
            "operator clicked one component in the live 3-D twin. Give a detailed "
            "but concise status (3-5 sentences): current condition, anything "
            "concerning in the readings, the most likely cause if degraded, and the "
            "recommended action. Name the specific readings. No preamble.")
        user = (f"Machine: {machine}\nDomain: {domain}\n"
                f"Component: {name} (type: {atype}, status: {status})\n"
                f"Live readings: {_json.dumps(metrics, default=str)}")
        resp = _anthropic().messages.create(
            model=config.CLAUDE_MODEL, max_tokens=350,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in resp.content if b.type == "text").strip() or _stub()
    except Exception as e:
        logger.warning("asset_status failed (%s); stub", e)
        return _stub()


# ── Work order generation (AS9100-compliant MRO documentation) ──

class WorkOrderStep(BaseModel):
    step: int = Field(description="Step number")
    action: str = Field(description="What the technician does")
    criteria: str = Field(description="Acceptance/inspection criteria")
    safety: str = Field(default="", description="Safety warning if applicable")

class WorkOrder(BaseModel):
    wo_number: str = Field(description="Work order number, e.g. WO-2026-001")
    ata_chapter: str = Field(description="ATA chapter reference, e.g. ATA 72 - Engine")
    priority: str = Field(description="AOG, Critical, Routine, or Scheduled")
    compliance_ref: str = Field(description="Regulatory reference, e.g. AS9100D Clause 8.5.1")
    fault_description: str = Field(description="Clear description of the fault")
    root_cause: str = Field(description="Identified or suspected root cause")
    steps: list[WorkOrderStep] = Field(description="Ordered repair/verification steps")
    estimated_hours: float = Field(description="Estimated labour hours")
    parts_required: list[str] = Field(default_factory=list)
    sign_off: str = Field(default="Level II Inspector", description="Required sign-off authority")


def generate_work_order(diagnostics: dict, machine: str) -> WorkOrder:
    """Generate an AS9100-compliant maintenance work order from diagnosis results."""
    comps = diagnostics.get("components", [])
    findings = diagnostics.get("findings", [])
    sensors = diagnostics.get("sensors", [])

    def _stub() -> WorkOrder:
        return WorkOrder(
            wo_number="WO-2026-001",
            ata_chapter="ATA 72 - Engine",
            priority="AOG" if any(f.get("severity") == "critical" for f in findings) else "Routine",
            compliance_ref="AS9100D Clause 8.5.1 / EASA Part 145.A.45",
            fault_description="Turbine hot-section degradation detected by 3-tier behavior engine",
            root_cause="Suspected blade erosion or nozzle coking based on EGT deviation pattern",
            steps=[
                WorkOrderStep(step=1, action="Apply LOTO to test rig", criteria="Zero energy state verified", safety="Confirm fuel isolation before approach"),
                WorkOrderStep(step=2, action="Borescope hot section per CMM 72-00-00", criteria="No blade tip loss >0.5mm, no nozzle blockage >20%"),
                WorkOrderStep(step=3, action="If fouled: chemical clean combustor nozzles", criteria="Spray pattern uniform across all nozzles"),
                WorkOrderStep(step=4, action="If eroded: replace affected turbine blades", criteria="New blades within tip clearance spec per AMM"),
                WorkOrderStep(step=5, action="Reassemble and ground run", criteria="EGT within limits, N1 stable, vibration <1.0g"),
                WorkOrderStep(step=6, action="Digital twin resync and sign-off", criteria="All sensor readings nominal, fault code cleared"),
            ],
            estimated_hours=4.5,
            parts_required=["Turbine blade set (if eroded)", "Combustor nozzle cleaning kit", "Borescope probe tip"],
            sign_off="Level II Inspector per EASA Part 145",
        )

    if not config.claude_enabled:
        return _stub()
    try:
        import json as _json
        system = (
            "You are an aerospace MRO documentation system. Generate an AS9100-compliant "
            "maintenance work order from this fault diagnosis. Use correct ATA chapter "
            "references. Each step must include acceptance criteria and safety warnings "
            "where applicable. Include EASA Part 145 and FAA 14 CFR 145 references. "
            "Language must be precise enough for a Level II-certified technician. "
            "Estimate realistic labour hours and list specific parts/tools needed.")
        resp = _anthropic().messages.parse(
            model=config.CLAUDE_MODEL, max_tokens=4000,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content":
                f"Machine: {machine}\nDiagnostics: {_json.dumps(diagnostics, default=str)[:6000]}"}],
            output_format=WorkOrder)
        return resp.parsed_output or _stub()
    except Exception as e:
        logger.warning("generate_work_order failed (%s); stub", e)
        return _stub()


# ── Predictive alert (proactive time-to-event warning) ──

def predictive_alert(prediction: dict, machine: str) -> str | None:
    """If any RUL entry is within the horizon, generate a specific actionable alert."""
    rul = prediction.get("rul", [])
    crossings = [r for r in rul if r.get("within_horizon")]
    if not crossings:
        return None

    # The prediction engine emits RUL entries in dict-iteration order, not by
    # urgency — sort by projected time-to-limit so crossings[0] is the soonest.
    crossings.sort(key=lambda c: c.get("time_to_limit_min")
                   if c.get("time_to_limit_min") is not None else float("inf"))
    r = crossings[0]  # most urgent

    def _stub() -> str:
        return (f"PREDICTIVE ALERT: {r['mode']} projected to be reached in "
                f"~{r['time_to_limit_min']:.0f} minutes at current degradation rate. "
                f"Recommend reducing thrust and scheduling inspection.")

    if not config.claude_enabled:
        return _stub()
    try:
        import json as _json
        system = (
            "You are a predictive maintenance alert system for a turbine test rig. "
            "Generate a single ACTIONABLE alert (2-3 sentences). Name the parameter, "
            "the projected time to limit crossing, and the immediate action required. "
            "Be specific and urgent but professional. No preamble.")
        resp = _anthropic().messages.create(
            model=config.CLAUDE_MODEL, max_tokens=200,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content":
                f"Machine: {machine}\n"
                f"Limit crossing: {_json.dumps(r)}\n"
                f"Full prediction: {_json.dumps(prediction, default=str)[:3000]}"}])
        return "".join(b.text for b in resp.content if b.type == "text").strip() or _stub()
    except Exception as e:
        logger.warning("predictive_alert failed (%s); stub", e)
        return _stub()


# ── Cascade reasoning (cross-system failure propagation) ──

def cascade_analysis(diagnostics: dict, prediction: dict, machine: str) -> str:
    """Reason about multi-system failure cascades — how degradation in one
    subsystem propagates to others."""
    def _stub() -> str:
        comps = diagnostics.get("components", [])
        bad = [c for c in comps if (c.get("health") or 1) < 0.7]
        if not bad:
            return "No cascade risks identified. All subsystems operating within margins."
        names = [c.get("name") or "a subsystem" for c in bad]
        return (f"Degradation detected in {', '.join(names)}. "
                f"If uncorrected, bearing wear can propagate to oil system stress "
                f"(elevated oil temp → reduced lubrication → accelerated wear cycle). "
                f"Monitor oil pressure closely and consider preemptive shutdown if oil temp exceeds 85C.")

    if not config.claude_enabled:
        return _stub()
    try:
        import json as _json
        system = (
            "You are an aerospace systems engineer specializing in failure mode cascade "
            "analysis. Given live turbine telemetry and a forward prediction, identify "
            "if any degradation in one subsystem is likely to propagate to another. "
            "Format each cascade as: [System A] degradation -> [System B] impact in ~N "
            "minutes because [physics reason]. Be specific and grounded in the data. "
            "If no cascades are likely, say so clearly. Max 4-5 sentences.")
        payload = {"diagnostics": diagnostics, "prediction": prediction}
        resp = _anthropic().messages.create(
            model=config.CLAUDE_MODEL, max_tokens=600,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content":
                f"Machine: {machine}\n{_json.dumps(payload, default=str)[:6000]}"}])
        return "".join(b.text for b in resp.content if b.type == "text").strip() or _stub()
    except Exception as e:
        logger.warning("cascade_analysis failed (%s); stub", e)
        return _stub()


# ── Multi-turn troubleshooting chatbot (AI Mechanic) ──

class TroubleshootReply(BaseModel):
    reply: str = Field(description="The mechanic's conversational response")
    hypothesis: str = Field(default="", description="Current leading fault hypothesis")
    confidence: float = Field(default=0.0, description="Confidence in the hypothesis 0-1")
    resolved: bool = Field(default=False, description="True when diagnosis is conclusive")


def troubleshoot_chat(history: list[dict], message: str,
                      diagnostics: dict, machine: str) -> TroubleshootReply:
    """Multi-turn diagnostic chatbot — asks clarifying questions like an
    experienced mechanic, narrows fault hypothesis with each answer."""
    def _stub() -> TroubleshootReply:
        turn = len([h for h in history if h.get("role") == "user"]) + 1
        if turn <= 1:
            return TroubleshootReply(
                reply="I see you've got some readings to discuss. Let me pull up "
                      "the sensor data. What's the primary symptom you're seeing — "
                      "is it a temperature issue, vibration, oil pressure, or something else?",
                hypothesis="", confidence=0.0, resolved=False)
        if turn == 2:
            return TroubleshootReply(
                reply="Got it. When did this start — was it sudden or a gradual trend? "
                      "And did you change throttle settings recently?",
                hypothesis="Possible hot-section degradation", confidence=0.3, resolved=False)
        return TroubleshootReply(
            reply="Based on the EGT trend and your answers, I'm fairly confident "
                  "this is early-stage blade erosion. The physics residual confirms "
                  "the measured EGT is higher than what fuel flow and N1 can explain. "
                  "Recommend a borescope inspection of the HP turbine.",
            hypothesis="Blade erosion (HP turbine)", confidence=0.85, resolved=True)

    if not config.claude_enabled:
        return _stub()
    try:
        import json as _json
        msgs = [{"role": h["role"], "content": h["content"]} for h in history[-10:]]
        msgs.append({"role": "user", "content": message})
        system = (
            "You are an experienced gas turbine MRO mechanic helping a technician "
            "troubleshoot a live engine on a test rig. You have access to the current "
            "sensor readings and physics residuals. Ask pointed diagnostic questions "
            "(1-2 per turn) to narrow down the fault. Be conversational but technical. "
            "When you have enough information, declare your hypothesis with confidence. "
            "Reference specific sensor values and ATA chapter numbers. "
            f"Current diagnostics: {_json.dumps(diagnostics, default=str)[:3000]}")
        resp = _anthropic().messages.parse(
            model=config.CLAUDE_MODEL, max_tokens=500,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=msgs, output_format=TroubleshootReply)
        return resp.parsed_output or _stub()
    except Exception as e:
        logger.warning("troubleshoot_chat failed (%s); stub", e)
        return _stub()


# ── Parts procurement agent ──

class PartEntry(BaseModel):
    part_number: str = Field(description="Part number / catalog reference")
    description: str = Field(description="What the part is")
    quantity: int = Field(default=1, description="How many needed")
    estimated_cost_usd: float = Field(default=0, description="Estimated unit cost")
    lead_time: str = Field(default="", description="Expected lead time")
    source: str = Field(default="", description="Supplier or stock location")

class ProcurementList(BaseModel):
    work_order_ref: str = Field(description="Reference work order number")
    total_estimated_cost: float = Field(description="Total estimated parts cost USD")
    aog_available: bool = Field(description="Whether all critical parts are AOG-stocked")
    parts: list[PartEntry] = Field(description="Parts needed for the repair")
    notes: str = Field(default="", description="Procurement notes or warnings")


def parts_procurement_agent(work_order: dict, machine: str) -> ProcurementList:
    """From a work order, identify specific part numbers, quantities, lead times,
    and estimated costs for the repair."""
    def _stub() -> ProcurementList:
        return ProcurementList(
            work_order_ref=work_order.get("wo_number", "WO-2026-001"),
            total_estimated_cost=18500.0,
            aog_available=True,
            parts=[
                PartEntry(part_number="CFM56-5B-72-001", description="HP Turbine blade set (Stage 1)",
                          quantity=1, estimated_cost_usd=12000, lead_time="AOG stock — 24h",
                          source="Collins MRO Singapore hub"),
                PartEntry(part_number="CFM56-5B-72-045", description="Combustor nozzle seal ring",
                          quantity=2, estimated_cost_usd=850, lead_time="3-5 days",
                          source="Safran Aircraft Engines"),
                PartEntry(part_number="GE-BSK-420-A", description="Borescope probe tip (8mm flex)",
                          quantity=1, estimated_cost_usd=320, lead_time="In-house tooling",
                          source="Tool crib"),
                PartEntry(part_number="CHEM-CLEAN-NT200", description="Chemical cleaning solution (20L)",
                          quantity=1, estimated_cost_usd=180, lead_time="In stock",
                          source="Consumables store"),
                PartEntry(part_number="R410A-12KG", description="R-410A refrigerant (chiller)",
                          quantity=1, estimated_cost_usd=95, lead_time="In stock",
                          source="HVAC stores"),
            ],
            notes="Critical path: HP turbine blade set. Collins Singapore hub confirms AOG "
                  "availability. Recommend pre-positioning before engine shutdown to minimize "
                  "downtime. Estimated total repair: 4.5 hours once parts are on hand.")

    if not config.claude_enabled:
        return _stub()
    try:
        import json as _json
        system = (
            "You are an aerospace MRO parts procurement specialist. Given a maintenance "
            "work order, identify the specific parts needed: part numbers (use realistic "
            "manufacturer catalog references for CFM56/LEAP-class engines), quantities, "
            "estimated costs in USD, lead times, and likely sources. Mark whether all "
            "AOG-critical parts are available within 24 hours. Be specific and realistic.")
        resp = _anthropic().messages.parse(
            model=config.CLAUDE_MODEL, max_tokens=1500,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content":
                f"Machine: {machine}\nWork Order: {_json.dumps(work_order, default=str)[:4000]}"}],
            output_format=ProcurementList)
        return resp.parsed_output or _stub()
    except Exception as e:
        logger.warning("parts_procurement failed (%s); stub", e)
        return _stub()


# ── Incident report generator ──

class IncidentReport(BaseModel):
    report_id: str = Field(description="Incident report number")
    classification: str = Field(description="ATA chapter + fault classification")
    aircraft_engine: str = Field(description="Engine type and serial/rig ID")
    timestamp: str = Field(description="When the incident was detected")
    symptoms: list[str] = Field(description="Observed symptoms with values")
    physics_evidence: str = Field(description="Physics residual analysis")
    probable_cause: str = Field(description="Most likely root cause")
    corrective_action: str = Field(description="Action taken or recommended")
    regulatory_closure: str = Field(description="EASA/FAA regulatory references")
    return_to_service: str = Field(description="Criteria for return to service")


def generate_incident_report(diagnostics: dict, findings: list,
                             machine: str) -> IncidentReport:
    """Generate a formal MRO incident report with regulatory closure references."""
    def _stub() -> IncidentReport:
        return IncidentReport(
            report_id="IR-2026-0627-001",
            classification="ATA 72-50 — Turbine Section, Hot-Section Degradation",
            aircraft_engine=f"{machine} — MRO Test Rig",
            timestamp="2026-06-27T14:32:00Z",
            symptoms=["EGT deviation +3.7σ above baseline (652°C vs 642°C mean)",
                      "Physics residual: measured EGT exceeds model prediction by 23°C",
                      "N1 droop: shaft speed 40 RPM below nominal at same throttle"],
            physics_evidence="The Brayton-cycle residual model indicates the measured EGT "
                           "cannot be explained by current fuel flow and N1 alone. The "
                           "+23°C excess is consistent with 0.3mm blade tip erosion or "
                           "15% nozzle area blockage from coking.",
            probable_cause="Turbine blade erosion (HP Stage 1) with possible secondary "
                          "nozzle coking. Degradation rate: approximately 2°C/hour at "
                          "cruise throttle.",
            corrective_action="1. Borescope HP turbine per CMM 72-00-00\n"
                             "2. If blade tip loss >0.5mm: replace blade set\n"
                             "3. If nozzle blockage >20%: chemical clean\n"
                             "4. Ground run verification: EGT within limits",
            regulatory_closure="EASA Part 145.A.45(b) — maintenance data requirements. "
                             "AS9100D Clause 8.5.1 — production and service provision. "
                             "FAA AC 43-218 — engine borescope inspection guidance.",
            return_to_service="EGT within ±15°C of baseline at stabilized ground run "
                            "(85% N1, 10 min). Vibration <1.0g. Oil temp/press nominal. "
                            "Level II inspector sign-off required.")

    if not config.claude_enabled:
        return _stub()
    try:
        import json as _json
        system = (
            "You are an aerospace MRO documentation specialist generating a formal "
            "incident report. Include ATA chapter classification, observed symptoms with "
            "specific sensor values, physics-based evidence, probable cause, corrective "
            "action steps, EASA/FAA regulatory closure references, and return-to-service "
            "acceptance criteria. Be precise enough for regulatory submission.")
        resp = _anthropic().messages.parse(
            model=config.CLAUDE_MODEL, max_tokens=1500,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content":
                f"Machine: {machine}\nDiagnostics: {_json.dumps(diagnostics, default=str)[:4000]}\n"
                f"Findings: {_json.dumps(findings[:5], default=str)[:2000]}"}],
            output_format=IncidentReport)
        return resp.parsed_output or _stub()
    except Exception as e:
        logger.warning("incident_report failed (%s); stub", e)
        return _stub()


def scenario_brief(prompt: str, machine: str, sensors: list[str]) -> ScenarioBrief:
    """Claude → structured scenario brief for the GoalCert engine. Falls back to a stub."""
    if not config.claude_enabled:
        return _scenario_stub(prompt)
    system = (
        "You design MRO training/what-if scenarios for an aerospace digital twin. "
        "Given a machine, its sensors, and a request, produce a concise, realistic "
        "fault scenario with technician steps. Keep it grounded and specific.")
    try:
        client = _anthropic()
        resp = client.messages.parse(
            model=config.CLAUDE_MODEL,
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content":
                f"Machine: {machine}\nSensors: {', '.join(sensors)}\n"
                f"Scenario request: {prompt}"}],
            output_format=ScenarioBrief,
        )
        return resp.parsed_output or _scenario_stub(prompt)
    except Exception as e:  # noqa: BLE001
        logger.warning("scenario brief failed (%s); using stub", e)
        return _scenario_stub(prompt)


# ── Generic, per-twin Scenario / Fault engine ─────────────────────────
# Works for ANY twin: the agent reads the machine's own fault catalogue + live
# signals and authors a runnable spec, which is then projected on the twin's
# physics (non-destructive). Scenarios = external conditions; faults = degraded
# components — both ultimately drive the same physics via (fault, control).

class AuthoredSim(BaseModel):
    title: str = Field(description="Short, specific title for the situation/fault.")
    fault: str = Field(description="EXACTLY one fault id from the catalogue, or "
                                   "'none' for a pure operating-condition scenario.")
    severity: float = Field(description="0..1 how aggressive / degraded.")
    control: float = Field(description="0..1 machine load during the run "
                                       "(turbine throttle / EDM machining intensity).")
    horizon_min: float = Field(description="Minutes to project forward.")
    rationale: str = Field(description="Why these parameters model the request for THIS machine.")
    expected_outcome: str = Field(description="One-sentence prediction of the result.")


def author_sim(description: str, machine: str, domain: str, kind: str,
               faults: list, signals: list, horizon_min: float = 120.0) -> AuthoredSim:
    """Agent: turn a natural-language situation/fault into a runnable spec for the
    given twin. `faults` is [{id,label}] from the twin's own catalogue; `kind` is
    'scenario' (external factors) or 'fault' (component degradation)."""
    fault_ids = {f.get("id") for f in faults}

    def _stub() -> AuthoredSim:
        p = (description or "").lower()
        fid = "none"
        for f in faults:
            if f["id"].split("_")[0] in p or f["id"] in p or f.get("label", "").lower() in p:
                fid = f["id"]
                break
        return AuthoredSim(
            title=(description or kind).strip()[:60] or kind.title(),
            fault=fid, severity=0.85, control=0.85, horizon_min=horizon_min,
            rationale=f"Mapped the request to the '{fid}' physics lever.",
            expected_outcome="")

    if not config.claude_enabled:
        return _stub()
    catalog = "\n".join(f"  - {f['id']}: {f.get('label','')}" for f in faults) or "  (none)"
    if kind == "scenario":
        kind_hint = ("an EXTERNAL operating SITUATION (ambient conditions, production "
                     "load / duty cycle, supply or material quality, environment). Map it "
                     "to the closest fault id that such conditions would induce — or 'none' "
                     "if it is purely a load/condition change — and pick a realistic machine "
                     "load (control).")
    else:
        kind_hint = ("a COMPONENT FAULT or degradation. Choose the single best-matching "
                     "fault id and a severity that clearly reveals it.")
    system = (
        f"You are the Scenario & Fault engine for a {machine} digital twin. The "
        f"operator describes {kind_hint}\n"
        f"Available fault ids for THIS machine:\n{catalog}\n"
        f"Available live signals: {', '.join(signals[:24])}.\n"
        "Produce a runnable spec: 'fault' MUST be exactly one of the ids above or "
        "'none'; severity 0..1; control 0..1; horizon_min realistic for the request. "
        "Be specific to this machine and these signals.")
    try:
        resp = _anthropic().messages.parse(
            model=config.CLAUDE_MODEL, max_tokens=1000,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content":
                f"Machine: {machine}\nKind: {kind}\nRequest: {description}"}],
            output_format=AuthoredSim)
        spec = resp.parsed_output or _stub()
        if spec.fault not in fault_ids and spec.fault != "none":
            spec.fault = _stub().fault
        return spec
    except Exception as e:  # noqa: BLE001
        logger.warning("author_sim failed (%s); stub", e)
        return _stub()


def analyze_projection(spec: dict, projection: dict, machine: str, domain: str = "") -> str:
    """Agent: plain-English analysis of a what-if projection for ANY twin — what
    happens, which subsystem leads the degradation, time-to-limit, and the
    precautions/maintenance to be ready. Stub falls back to a numeric summary."""
    rul = projection.get("rul", [])
    events = projection.get("events", [])
    chn = projection.get("component_health_now", {}) or {}
    chh = projection.get("component_health_horizon", {}) or {}

    def _stub() -> str:
        bits = []
        crossings = [r for r in rul if r.get("within_horizon")]
        if crossings:
            c = min(crossings, key=lambda r: r.get("time_to_limit_min") or 1e9)
            bits.append(f"{c['mode']} is reached in about "
                        f"{(c.get('time_to_limit_min') or 0):.0f} minutes.")
        on = (chn.get("overall") or {}).get("health")
        oh = (chh.get("overall") or {}).get("health")
        if on is not None and oh is not None:
            bits.append(f"Overall health goes from {on*100:.0f}% to {oh*100:.0f}% "
                        f"over the horizon.")
        if events:
            bits.append("Detections (in order): " +
                        ", ".join(e.get("behavior_id", "") for e in events) + ".")
        return " ".join(bits) or ("No operating limit is crossed within the horizon — "
                                  "the machine stays within margins.")

    if not config.claude_enabled:
        return _stub()
    try:
        import json as _json
        payload = {"spec": spec, "rul": rul, "events": events,
                   "health_now": chn, "health_horizon": chh,
                   "final_frame": (projection.get("trajectory") or [{}])[-1]}
        system = (
            f"You are a senior maintenance engineer for a {machine}. Given a what-if "
            "scenario/fault and its physics projection, explain in plain English: what "
            "happens to the machine, which subsystem leads the degradation, the time-to-"
            "limit, and the precautions / maintenance to have ready. Be specific and "
            "grounded in the numbers. 4-6 sentences, no preamble.")
        resp = _anthropic().messages.create(
            model=config.CLAUDE_MODEL, max_tokens=600,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content":
                f"Machine: {machine}\n{_json.dumps(payload, default=str)[:6500]}"}])
        return "".join(b.text for b in resp.content if b.type == "text").strip() or _stub()
    except Exception as e:  # noqa: BLE001
        logger.warning("analyze_projection failed (%s); stub", e)
        return _stub()


# ── Snapshot agents (run any agent on a telemetry snapshot — live OR simulated) ──

def diagnose_snapshot(machine: str, domain: str, latest: dict,
                      findings: list, components: list | None = None) -> str:
    """Diagnosis from a telemetry snapshot — works for any twin (incl. the
    simulated facility twins), grounded in whatever signals it is given."""
    findings = findings or []

    def _stub() -> str:
        crit = [f for f in findings if f.get("severity") == "critical"]
        return (f"{machine}: {len(findings)} active finding(s), {len(crit)} critical. "
                f"Review the out-of-band signals and inspect the flagged assets.")

    if not config.claude_enabled:
        return _stub()
    try:
        import json as _json
        system = (
            f"You are a maintenance engineer for a {machine}. Given the live "
            "telemetry and active findings, produce a concise diagnosis: overall "
            "condition, the 2-3 signals/components of most concern, the most likely "
            "root cause, and prioritised actions. Short sections, grounded in the "
            "numbers, no preamble.")
        user = (f"Machine: {machine}\nDomain: {domain}\n"
                f"Signals: {_json.dumps(latest, default=str)}\n"
                f"Findings: {_json.dumps(findings, default=str)[:1500]}")
        if components:
            user += f"\nComponents: {_json.dumps(components, default=str)[:1200]}"
        resp = _anthropic().messages.create(
            model=config.CLAUDE_MODEL, max_tokens=700,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in resp.content if b.type == "text").strip() or _stub()
    except Exception as e:  # noqa: BLE001
        logger.warning("diagnose_snapshot failed (%s); stub", e)
        return _stub()


def forecast_snapshot(machine: str, domain: str, latest: dict,
                      horizon_label: str, context: str = "") -> str:
    """Qualitative forecast from a telemetry snapshot over a horizon — for any
    twin. `context` lets a scenario/fault frame the forecast (the assumed
    situation)."""
    def _stub() -> str:
        return (f"Over the next {horizon_label}, {machine} is expected to continue "
                f"near its current operating point; watch any signals close to their "
                f"limits and keep spares ready for the most-loaded assets.")

    if not config.claude_enabled:
        return _stub()
    try:
        import json as _json
        system = (
            f"You are a reliability engineer for a {machine}. Given the current "
            f"telemetry, forecast how the machine is likely to behave over the next "
            f"{horizon_label}: which signals trend toward their limits, the main "
            f"risks, and what to watch or pre-empt. {context} Be specific and grounded "
            "in the numbers. 4-6 sentences, no preamble.")
        resp = _anthropic().messages.create(
            model=config.CLAUDE_MODEL, max_tokens=600,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content":
                f"Machine: {machine}\nDomain: {domain}\n"
                f"Signals: {_json.dumps(latest, default=str)}"}])
        return "".join(b.text for b in resp.content if b.type == "text").strip() or _stub()
    except Exception as e:  # noqa: BLE001
        logger.warning("forecast_snapshot failed (%s); stub", e)
        return _stub()


# ── Interactive maintenance TRAINING agent ────────────────────────────
# A full ordered repair procedure for a scenario/fault where every step also
# carries the consequence of skipping it or doing it out of order — the UI turns
# this into an interactive trainer.

class TrainStep(BaseModel):
    id: str = Field(description="Short id like 'S1','S2' in the CORRECT order.")
    title: str = Field(description="Short step name.")
    action: str = Field(description="Exactly what the technician does.")
    rationale: str = Field(description="Why this step matters / what it achieves.")
    criteria: str = Field(description="How to confirm it was done correctly.")
    safety: bool = Field(default=False, description="True if this is a safety / isolation / LOTO step.")
    requires: list[str] = Field(default_factory=list,
        description="Ids of steps that MUST be completed before this one.")
    skip_consequence: str = Field(description="What goes wrong on the machine if this step is skipped.")
    wrong_order_consequence: str = Field(description="What goes wrong if done before its prerequisites.")


class MaintenanceProcedure(BaseModel):
    title: str = Field(description="Procedure title for this fault/scenario.")
    fault: str = Field(description="The fault id being repaired, or 'none'.")
    summary: str = Field(description="1-2 sentence overview of the repair.")
    steps: list[TrainStep] = Field(description="The correctly-ordered repair steps.")
    success_criteria: str = Field(description="How to confirm the machine is fully restored.")
    common_mistakes: list[str] = Field(default_factory=list,
        description="Frequent trainee mistakes and why they are dangerous.")


def build_procedure(machine: str, domain: str, fault: str,
                    scenario_title: str = "", scenario_context: str = "") -> MaintenanceProcedure:
    """Master trainer: a complete ordered repair procedure for THIS fault on THIS
    machine, with per-step skip / wrong-order consequences for interactive training."""
    def _stub() -> MaintenanceProcedure:
        return MaintenanceProcedure(
            title=f"Repair: {scenario_title or fault}", fault=fault or "none",
            summary="Isolate, diagnose, repair, verify.",
            steps=[
                TrainStep(id="S1", title="Isolate & make safe",
                          action="Apply LOTO and confirm a zero-energy state.",
                          rationale="Protects the technician before any intervention.",
                          criteria="Energy isolated and verified.", safety=True, requires=[],
                          skip_consequence="Live-energy hazard during the repair.",
                          wrong_order_consequence="N/A — this must be first."),
                TrainStep(id="S2", title="Diagnose",
                          action="Confirm the faulted component from the telemetry.",
                          rationale="Targets the real root cause.", criteria="Root cause confirmed.",
                          requires=["S1"], skip_consequence="You may repair the wrong component.",
                          wrong_order_consequence="Diagnosing live is unsafe and inaccurate."),
                TrainStep(id="S3", title="Repair",
                          action="Service or replace the faulted component.",
                          rationale="Restores the machine.", criteria="Component within spec.",
                          requires=["S1", "S2"], skip_consequence="The fault persists.",
                          wrong_order_consequence="Repairing the wrong part wastes the window."),
                TrainStep(id="S4", title="Verify & return to service",
                          action="Re-run and confirm readings nominal.",
                          rationale="Proves the fix.", criteria="All signals within limits.",
                          requires=["S1", "S2", "S3"], skip_consequence="Undetected residual fault.",
                          wrong_order_consequence="Cannot verify before repairing."),
            ],
            success_criteria="All signals within limits and the fault cleared.",
            common_mistakes=["Skipping isolation (safety).", "Repairing before diagnosing.",
                             "Returning to service without verification."])

    if not config.claude_enabled:
        return _stub()
    try:
        ctx = (f" arising from the situation: {scenario_title}. {scenario_context}"
               if scenario_title else "")
        system = (
            f"You are a master maintenance trainer for a {machine}. Produce a complete, "
            f"correctly-ordered repair procedure a trainee can follow for the fault "
            f"'{fault}'{ctx}. For EACH step give: a short title, the action, the rationale, "
            "the acceptance criteria, whether it is a safety/isolation step, the ids of "
            "steps that must come first (requires), the consequence of SKIPPING it, and the "
            "consequence of doing it OUT OF ORDER. Order steps safety-first, diagnose before "
            "repair, verify last. List common trainee mistakes. Be specific to this machine "
            "and fault — name real components and signals.")
        resp = _anthropic().messages.parse(
            model=config.CLAUDE_MODEL, max_tokens=8000,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content":
                f"Machine: {machine}\nDomain: {domain}\nFault: {fault}\n"
                f"Scenario: {scenario_title}\nContext: {scenario_context}"}],
            output_format=MaintenanceProcedure)
        return resp.parsed_output or _stub()
    except Exception as e:  # noqa: BLE001
        logger.warning("build_procedure failed (%s); stub", e)
        return _stub()


def _chat(messages: list, system: str, max_tokens: int = 600) -> str:
    """Shared multi-turn chat helper. `messages` is [{role, content}]."""
    if not config.claude_enabled:
        last = next((m.get("content", "") for m in reversed(messages or [])
                     if m.get("role") == "user"), "")
        return ("AI chat is in stub mode (no ANTHROPIC_API_KEY set). You said: "
                f"{last[:140]}")
    try:
        norm = [{"role": ("assistant" if m.get("role") == "assistant" else "user"),
                 "content": str(m.get("content", ""))}
                for m in (messages or []) if m.get("content")]
        if not norm:
            norm = [{"role": "user", "content": "Hello"}]
        resp = _anthropic().messages.create(
            model=config.CLAUDE_MODEL, max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=norm)
        return "".join(b.text for b in resp.content if b.type == "text").strip() or "(no reply)"
    except Exception as e:  # noqa: BLE001
        logger.warning("_chat failed (%s)", e)
        return "Sorry — I couldn't reach the AI just now. Try again."


def scenario_chat(messages: list, context: dict, machine: str) -> str:
    """Interactive training coach: knows the scenario, the procedure and the
    trainee's progress, and explains the outcome of ANY decision they explore."""
    import json as _json
    system = (
        f"You are an interactive maintenance TRAINING coach for a {machine}. The trainee is "
        "working a scenario and its repair procedure. Teach by doing: answer questions, and "
        "when they ask 'what if I skip / reorder / do X', explain the concrete consequence "
        "on the machine, why the correct flow matters, and the safe next move. Be concise "
        "(3-6 sentences), specific to the steps and signals, and encouraging. You may "
        "reference step ids. Context:\n" + _json.dumps(context, default=str)[:5000])
    return _chat(messages, system, max_tokens=700)


def dashboard_chat(messages: list, snapshot: dict, machine: str) -> str:
    """Live operations assistant: answers questions about the CURRENT machine
    status from its telemetry + findings."""
    import json as _json
    system = (
        f"You are the live operations assistant for a {machine}. Answer the operator's "
        "questions about the CURRENT status using the telemetry and findings below. Be "
        "concise and specific, name the signals and their values, and flag anything "
        "concerning with a clear next action. Current snapshot:\n"
        + _json.dumps(snapshot, default=str)[:4000])
    return _chat(messages, system, max_tokens=600)
