# Turbine Digital Twin — backend ↔ 3D integration contract

This is the contract the **3D layer** (the engine's stand-in, since we have no
real turbine) uses to drive the backend twin. The 3D model produces sensor
readings (or just a throttle); the backend runs the **physics + behaviours +
diagnosis** and returns live health, findings, and incidents.

All endpoints are on the NextXR backend (`http://localhost:8000`). The orchestrator
(collins-demo) can proxy these, or the 3D layer can call them directly.

## 1. Create the turbine twin (once)

```
POST /api/v1/twins
{ "name": "Engine TR-01", "domain": "turbine-engine" }
```

Seeds one engine (`aero:TurbineTestRig`) + its modules
(`aero:CompressorModule`, `CombustorModule`, `TurbineModule`) + a 7-sensor suite
(EGT, N1, N2, fuel flow, vibration, oil temp, oil pressure), each wired
`nxr:monitors → engine` and `sosa:observes → <observable property>`.

Response → `twin.tenant_id` (use everywhere below) and `twin.seed_asset_id`
(the engine entity id — what readings target and what the 3D hotspots bind to).

List the entities (engine, modules, sensors) the 3D layer binds to:

```
GET /api/v1/entities?tenant=<tenant>&label=PhysicalAsset&limit=50
```

## 2. Stream sensor readings from the 3D layer

### Signal keys (canonical)

| Signal key                  | Meaning              | Unit          |
|-----------------------------|----------------------|---------------|
| `aero:exhaustGasTemp`       | EGT                  | DEG_C         |
| `aero:shaftSpeedN1`         | LP spool speed       | REV-PER-MIN   |
| `aero:shaftSpeedN2`         | HP spool speed       | REV-PER-MIN   |
| `aero:fuelFlow`             | Fuel mass flow       | KiloGM-PER-HR |
| `aero:vibrationG`           | Shaft vibration      | g             |
| `aero:enginePressureRatio`  | EPR                  | (ratio)       |
| `aero:oilTemperature`       | Oil temperature      | DEG_C         |
| `aero:oilPressure`          | Oil pressure         | PSI           |

### Push a full frame (recommended — one call per tick)

```
POST /api/v1/ingest/frame
{
  "tenant": "<tenant>",
  "entity_id": "<engine id>",          // optional; defaults to the twin's engine
  "readings": {
    "aero:exhaustGasTemp": 712.4,
    "aero:shaftSpeedN1": 5180,
    "aero:fuelFlow": 815,
    "aero:vibrationG": 0.6,
    "aero:oilTemperature": 71,
    "aero:oilPressure": 54
  },
  "ts": "2026-06-28T12:00:00Z"          // optional ISO-8601
}
```
`readings` may also be a list: `[{"signal": "...", "value": 712.4}, ...]`.
Response: `{ "accepted": N, "findings_this_frame": M }`.

Each reading flows through the behaviour registry → findings → change log +
event bus → diagnosis. Co-located values are stamped on the engine node so the
Tier-A physics residual can read EGT/fuel/N1 together.

### Or drive by throttle (backend physics produces the frame)

When the 3D layer only has a throttle (and optional fault to inject), let the
backend physics generate a consistent frame:

```
POST /api/v1/ingest/simulate
{
  "tenant": "<tenant>",
  "throttle": 0.95,                     // 0..1
  "fault": "blade_erosion",             // optional, see faults below
  "severity": 0.8,                      // 0..1
  "dt": 1.0                             // seconds advanced
}
```
Faults: `blade_erosion`, `nozzle_coking`, `compressor_fouling`, `bearing_wear`,
`oil_starvation`, `surge`, `none`. Response includes the generated `frame`.

## 3. Read live twin state (for the 3D HUD / hotspots)

```
GET /api/v1/ingest/<tenant>/state
```
```jsonc
{
  "entity_id": "...",
  "health": 0.49,                       // 0..1 physics health index
  "latest": { "aero:exhaustGasTemp": 712.4, ... },   // bind hotspots to these
  "residuals": { "aero:exhaustGasTemp": 56.3 },      // measured - physics-expected
  "findings": [ { "behaviorId": "aero.egt_redline", "severity": "critical",
                  "message": "..." }, ... ],
  "incidents": [ { "displayName": "Incident: 5 finding(s)...",
                   "severity": "critical", "status": "diagnosed" } ]
}
```

The 3D layer polls `/state` (or the SSE bus `GET /api/v1/bus/stream?tenant=...`)
and colours each sensor hotspot by its latest value vs. the redline, flashing the
ones named in `findings`.

## 4. What the backend owns (physics + reasoning)

- **Physics** (`turbine/physics.py`): Brayton-cycle EGT prediction, EPR, oil-temp,
  and a forward sim. Redlines: EGT 780 °C, oil 85 °C, oil-press 40 PSI, vib 2.0 g.
- **Behaviours** (`behaviors/aerospace/`): Tier-A EGT physics residual + surge/stall;
  Tier-B EGT & shaft baselines; Tier-C EGT redline, oil over-temp, oil-pressure
  low, vibration high.
- **Diagnosis** (`behaviors/diagnosis.py`): groups findings → incident → diagnosis
  → recommendation → action.

The 3D layer supplies only the sensor truth (or throttle); all detection and
reasoning is server-side, exactly as it would be against a real engine.
