# Porting Guide — 3D & BIM Generation

**Your role:** turn inputs into 3D. Image→3D (TRELLIS), drawing/floor-plan→3D, and
IFC→discipline-layer geometry. You produce **geometry + a job/report**; the Digital Twin
consumes it (attach a model to a twin, or map a building's layers). This is the one
platform that already has a dedicated home — the `apps/` repo — so your job is mostly
**consolidation**, not a fresh port.

---

## 1. Your source of truth in the reference

| Reference file | What it is |
|---|---|
| `collins-demo/orchestrator/pipeline3d/` | the production pipeline layers: `preprocess.py` (quality gate: isolate/enhance/normalize/frame), `params.py` (draft/standard/ultra sampler presets), `postprocess.py` (GLB validate/stats/repair) |
| `collins-demo/orchestrator/runpod_3d.py` | the RunPod TRELLIS client that drives preprocess → generate → postprocess, with the pipeline report |
| `collins-demo/orchestrator/tripo.py` | the Tripo fallback provider |
| `apps/trellis-worker/` | the **production GPU worker** (handler + Dockerfile + deploy guide) — full sampler params, multi-image |
| `apps/3d-platform/` | the existing **19-stage pipeline** (object route + drawing route) — your spine |
| `apps/2d-to-3d/` | drawing / floor-plan → furnished 3D scene |
| `collins-demo/orchestrator/bim_ifc.py` | IFC → discipline-layer GLB split (architecture/structure/plumbing/HVAC/electrical/fire) + element index |

## 2. Build ON your existing patterns

`apps/3d-platform` already has the modular 19-stage spine with a provider-abstracted
`reconstruct` stage. **Fold the demo's newer, better pieces into it** rather than keeping
two parallel pipelines:
- The demo's `pipeline3d/preprocess.py` is more advanced than the platform's early
  segment/enhance stages → merge it into the corresponding stages.
- `pipeline3d/params.py` presets + `runpod_3d.py`'s full-parameter payload → make these
  the platform's reconstruct-stage config (the platform's `reconstruct.py` was already
  updated to send full params — finish the consolidation).
- `pipeline3d/postprocess.py` (validate/stats/repair) → the platform's mesh stages.

## 3. Feature-by-feature mapping

| Feature | In the reference | Build in your platform |
|---|---|---|
| Image→3D quality gate | `pipeline3d/preprocess.py` | the pipeline's preprocess/segment/enhance stages |
| Sampler quality presets | `pipeline3d/params.py` (draft/standard/ultra) | reconstruct-stage config |
| Multi-image conditioning | `runpod_3d.start_image_task(extra_images=...)` + worker `run_multi_image` | pipeline input + worker (already supported) |
| Mesh post-processing | `pipeline3d/postprocess.py` | mesh validate/stats stages |
| Provider abstraction | `runpod_3d.py` / `tripo.py` | the reconstruct stage's provider switch (runpod/tripo/replicate/stub) |
| Production GPU worker | `apps/trellis-worker/` | **deploy it** (see its README) — this is what unlocks real quality |
| Drawing→3D | `apps/2d-to-3d/` + the pipeline's drawing route | keep as the drawing route |
| **IFC→discipline layers** | `bim_ifc.py` | the **conversion** half lives here (geometry); the **semantics** go to the Twin — see §4 |

## 4. BIM: you own conversion, the Twin owns semantics

`bim_ifc.py` does two jobs — split them:
- **You (Generation):** IFC → per-discipline GLB geometry + a raw `elements.json`
  (guid, class, discipline, storey, center, bounds). Pure conversion. Expose via
  `POST /bim/ingest` → `GET /bim/{id}/manifest` + `/bim/{id}/file/{name}`.
- **Digital Twin:** takes your `elements.json` and turns it into the building twin —
  fault-to-element overlay, X-ray mapping, live status per component. Not your concern.

This keeps you a stateless generation service and keeps building *state* with the twin.

## 5. Contract you must expose

The **3D & BIM Generation** block in [README.md](README.md#3d--bim-generation--apiv1generate):
`/image-to-3d`, `/drawing-to-3d`, `/jobs/{id}`, `/bim/ingest`, `/bim/{id}/manifest`,
`/bim/{id}/file/{name}`. Everything is **job-based** (submit → poll) because generation is
slow; return a `job_id` immediately and a `model_url` + `report` on completion.

## 6. Do NOT copy these demo shortcuts

- **TripoSR-era params** (`mc_resolution`, `foreground_ratio`) — dead for TRELLIS; use the
  real sampler presets from `params.py`.
- **Two parallel pipelines.** Don't keep `pipeline3d/` *and* `3d-platform/stages/` doing
  the same thing — consolidate into the 19-stage spine.
- **Coupling to a specific tenant/twin.** You're a generation service: take inputs, return
  geometry. Attaching a GLB to a twin is the Twin's job (or the hub's).
- **Skipping validation.** Always run `validate_glb` before returning a model_url — a
  corrupt GLB reaching the viewer is the #1 silent failure.

## 7. Acceptance criteria

- [ ] `POST /image-to-3d {images[], quality:"standard"}` → job → `GET /jobs/{id}` returns a validated GLB + a pipeline report (preprocess steps, params, mesh stats).
- [ ] Multi-image (2–4 views) produces a measurably better mesh than single-image.
- [ ] The production GPU worker is deployed and its `output.metadata` proves full-param sampling.
- [ ] `POST /bim/ingest` on the Duplex sample returns 5 discipline layers + `elements.json` (~1,100 elements).
- [ ] One consolidated pipeline — no duplicate stage logic between `pipeline3d/` and the platform.

**Recommended first PR:** fold `pipeline3d/` (preprocess/params/postprocess) into the
19-stage pipeline's stages and deploy the `trellis-worker`, so image→3D quality jumps
immediately with the config already written.
