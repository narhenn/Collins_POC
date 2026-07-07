# Handoff Package — Splitting the demo into four platforms + a hub

This folder is the **distribution kit** for turning the bundled Collins demo into
four independent platforms plus an integration hub. Hand each team three things:

1. **The architecture doc** (the shared `platform-architecture.html`) — the *what* and *why*.
2. **The reference implementation** (the `collins-demo/` folder) — the working prompts,
   physics, and logic to copy *behaviour* from.
3. **Their porting guide** (one file in this folder) — the *how, for their platform*:
   which reference files are their source of truth, how those map onto their existing
   codebase's patterns, and the exact API contract they must expose.

> **Why all three.** The reference folder alone is ambiguous — its code is written in the
> *demo's* idioms, not each platform's. A porting guide is what stops a team from pasting
> the demo's shortcuts in and throwing away what their platform is actually for. The
> shared contract (below) is what lets every team build **in parallel** and still snap
> together under the hub without renegotiation.

## The five deliverables

| Platform | Owns | Porting guide | Target repo |
|---|---|---|---|
| **Digital Twin** | the live, physics-grounded asset model, its telemetry, health, prediction, graph & BIM semantics | [porting-digital-twin.md](porting-digital-twin.md) | Digital Twin repo |
| **Agentic AI** | every LLM agent & workflow (diagnosis, work-orders, cascade, chat, …) | [porting-agentic-ai.md](porting-agentic-ai.md) | Agentic AI repo |
| **Scenario Engine** | authoring, running & scoring what-if and training scenarios | [porting-scenario-engine.md](porting-scenario-engine.md) | Scenario Engine repo |
| **3D & BIM Generation** | image→3D, drawing→3D, IFC→discipline-layers | [porting-generation.md](porting-generation.md) | Generation repo (`apps`) |
| **Integration Hub** | single entry point, auth, entitlements, composition | [hub-build-spec.md](hub-build-spec.md) | new hub repo |

## The golden rule: build to the contract

Every platform is an independent HTTP service. The hub only ever talks to these
services through the contract below — never through their internals. As long as each
team honours their slice of this contract, the hub composes them with zero coupling.

Base URL is per-deployment; the hub injects it. All bodies are JSON. `tenant` is the
twin/asset id that threads through every platform so they can talk about the same asset.

### Digital Twin — `/api/v1`
```
GET    /twins/templates                      -> [{key, label}]                 list domains
POST   /twins            {name, domain, options?} -> {tenant, domain}          create + seed
GET    /twins/{tenant}/state                 -> {health, latest, findings, incidents}
GET    /twins/{tenant}/diagnostics           -> {components[], sensors[], findings[]}
POST   /twins/{tenant}/step  {throttle?, fault?, severity?} -> {frame}         drive/inject
POST   /twins/{tenant}/running  {running}    -> {ok}                           freeze/resume
GET    /twins/{tenant}/predict?horizon_min=  -> {trajectory[], rul[], events[]}
POST   /twins/{tenant}/project {fault?, severity?, control?, horizon_min} -> {trajectory, rul}
GET    /twins/{tenant}/network               -> {geometry, vehicles[], route_status}  (fleet only)
GET    /twins/{tenant}/faults                -> [{id, label}]                  injectable faults
GET    /events/stream                        -> SSE/WS of findings + telemetry
```

### Agentic AI — `/api/v1/agents`
```
POST   /agents/run   {capability, tenant, context} -> {result}                one facade, many agents
        capability ∈ diagnose | analyze | narrate | work-order | cascade | alert
                    | procurement | incident-report | procedure | asset-status
POST   /agents/chat  {thread_id, message, context}  -> {reply}                with memory
GET    /agents/capabilities                          -> [{capability, needs}]  what it can do
```

### Scenario Engine — `/api/v1/scenario`
```
GET    /scenarios?domain=            -> {library[], presets[]}
GET    /faults?domain=               -> [{id, label}]
POST   /scenarios/author {description, tenant, domain} -> {spec}               NL -> runnable spec
POST   /runs   {tenant, spec}        -> {run_id}                              start a run
GET    /runs/{run_id}                -> {status, result, kpis}
GET    /runs/{run_id}/events         -> SSE/WS live run
POST   /training/procedure {tenant, fault} -> {procedure}                     guided repair
POST   /training/{run_id}/step {step_id, action} -> {consequence, score}
```

### 3D & BIM Generation — `/api/v1/generate`
```
POST   /image-to-3d  {images[], quality} -> {job_id}                          quality: draft|standard|ultra
POST   /drawing-to-3d {file, facility}   -> {job_id}
GET    /jobs/{job_id}                     -> {status, model_url, report}
POST   /bim/ingest   {ifc_file}           -> {building_id}                     background
GET    /bim/{building_id}/manifest        -> {disciplines[], storeys[], bounds}
GET    /bim/{building_id}/file/{name}     -> layer GLB / elements.json
```

### Integration Hub — `/`
```
GET    /capabilities                 -> merged manifest of every reachable platform
GET    /me/entitlements              -> {enabled: [digital-twin, agentic-ai, scenario, generation]}
*      /twin/*  /agents/*  /scenario/*  /generate/*   -> gateway-routed to the owning platform
```

## How each team works, in parallel

1. Stand up your service to satisfy **your slice of the contract** above — that's the
   only interface anyone depends on.
2. Use your porting guide to build the *behaviour* (copy prompts/physics/logic from the
   reference, re-expressed in your platform's patterns).
3. Test against the contract with mock data — you never need the other platforms running.
4. The hub team wires everything together once services are up; nothing about your
   internals leaks to them.

## What "done" looks like

The demo becomes a thin client that calls these four services through the hub. When you
can toggle a platform off in the entitlement manifest and the product degrades cleanly
to exactly the remaining capabilities, the split is complete.
