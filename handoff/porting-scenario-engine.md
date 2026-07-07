# Porting Guide — Scenario Engine

**Your role:** author, run, and score what-if and training scenarios. You *orchestrate* a
run — driving the Digital Twin's projection and, where useful, the Agentic AI — then
measure the outcome against KPIs. You don't own the physics (the Twin does) or the LLM
reasoning (Agentic AI does); you own the **scenario, the run, and the score.**

---

## 1. Your source of truth in the reference

| Reference file | What it is |
|---|---|
| `collins-demo/orchestrator/scenarios.py` | the curated scenario library + authored-scenario store (flat, in-memory) |
| `collins-demo/orchestrator/routes.py` (`SCENARIO_PRESETS`, `TWIN_FAULTS`, `/scenarios/*`, `/twins/scenarios`, `/twins/faults`, `/agents/sim/*`) | presets + fault catalogues per domain + run endpoints |
| `collins-demo/orchestrator/claude_client.py` (`author_sim`, `analyze_projection`, `scenario_chat`, `build_procedure`) | NL→spec authoring, outcome narration, training coach, procedure builder |
| `collins-demo/web/src/Scenario.jsx` | the two-tab UX: **Scenarios** (external situations) vs **Faults** (degraded components) → author → simulate |
| `collins-demo/web/src/Trainer.jsx` | the **interactive training simulator**: perform/skip steps, consequences, safety & order penalties, score & grade |
| `collins-demo/web/src/Maintenance.jsx` | the **AI Maintenance Director** cinematic run (visualization of an autonomous repair) |
| `nextxr-ontology/{edm,turbine,fleet}/scenario.py` | the per-domain fault catalogues (canonical fault ids) |

## 2. Build ON your existing patterns

Your platform (`goalcert-engine/backend/app/`) already has the real machinery the demo
faked with a flat list:
- `engine/scenario.py`, `engine/world.py`, `engine/environment.py`, `engine/events.py`,
  `engine/resolve/`, `engine/kpis.py`, `engine/result.py`, `engine/run.py` — a real
  scenario+world+KPI model.
- `scenarios/definitions/` + `scenarios/loader.py` — declarative scenario definitions.
- `services/run_manager.py`, `services/runner.py` — run orchestration.
- `api/` (`catalog`, `scenarios`, `runs`, `dashboard`), `ws/runs.py` — endpoints + live streaming.

**So the demo's flat `LIBRARY` list becomes scenario definitions your loader understands,
and its ad-hoc "run" becomes a real run through `run_manager` with KPIs and a result.**

## 3. Feature-by-feature mapping

| Feature | In the demo | Build in your platform |
|---|---|---|
| Scenario library | `scenarios.py` `LIBRARY` (list of dicts) | `scenarios/definitions/` entries loaded by `loader.py` |
| External-situation presets | `routes.py` `SCENARIO_PRESETS` per domain | scenario definitions tagged by domain |
| Fault catalogue | `routes.py` `TWIN_FAULTS` + `{domain}/scenario.py` | your `catalog` — source the canonical fault ids from the Twin's `/faults` |
| Author from NL | `author_sim()` (LLM) | your authoring flow — **call the Agentic AI** `author` capability, don't re-implement the LLM call |
| Run a scenario | demo `nextxr.project()` (physics) + `analyze_projection` | `run_manager` → **call the Twin** `POST /twins/{tenant}/project` for physics, then score |
| Outcome narrative | `analyze_projection()` (LLM) | call Agentic AI `analyze` capability |
| KPIs & result | *the demo has none* — this is your value-add | `engine/kpis.py` + `engine/result.py` — score every run objectively |
| Training simulator | `Trainer.jsx` grading + `build_procedure` | a **training run type**: steps from Agentic AI `procedure`, grading via your KPIs/result |
| AI Maintenance Director | `Maintenance.jsx` (frontend only) | a **run visualization** streamed over `ws/runs.py`; the *logic* is a run, the cinematic is UI |

## 4. Who calls whom (important — you're an orchestrator)

A scenario run is a **saga across three services**:
1. **You** own the scenario spec + run lifecycle + scoring.
2. For the **physics what-if**, you call the **Digital Twin**: `POST /twins/{tenant}/project`.
3. For **authoring** (NL→spec) and **narration/coaching**, you call the **Agentic AI**:
   `POST /agents/run {capability: author|analyze}`.
4. You stream progress over your websocket and persist the KPI result.

This is exactly why the split matters: the demo inlined all three; you keep only the
orchestration + scoring and *delegate* the physics and the language.

## 5. Contract you must expose

The **Scenario Engine** block in [README.md](README.md#scenario-engine--apiv1scenario) —
`/scenarios`, `/faults`, `/scenarios/author`, `/runs`, `/runs/{id}`, `/runs/{id}/events`,
plus the `/training/*` endpoints for the guided-repair simulator.

## 6. Do NOT copy these demo shortcuts

- **The flat in-memory `LIBRARY`/`_authored` lists.** Use declarative definitions +
  persistence so scenarios are versioned and shareable.
- **Re-calling the LLM directly** (`author_sim`, `analyze_projection` live in the demo's
  `claude_client`). Delegate those to the Agentic AI platform — you orchestrate, they reason.
- **Re-implementing physics.** Never simulate the fault yourself; always project through
  the Twin so results stay consistent with live monitoring.
- **Grading logic hard-coded in the React `Trainer`.** Move scoring server-side into your
  KPI/result engine so certifications are authoritative, not client-side.

## 7. Acceptance criteria

- [ ] `GET /scenarios?domain=tram-network` returns the presets; `GET /faults?domain=` returns the catalogue sourced from the Twin.
- [ ] `POST /runs {spec}` executes a run that calls the Twin's `/project`, streams events, and returns a **KPI-scored result**.
- [ ] `POST /scenarios/author` produces a runnable spec by delegating to the Agentic AI.
- [ ] A **training run** serves a procedure, accepts perform/skip per step, applies safety/order penalties, and returns a grade — all server-side.
- [ ] Works across EDM, turbine, and tram domains unchanged.

**Recommended first PR:** turn the demo's `LIBRARY` + one domain's presets into scenario
definitions, and wire a single run end-to-end that calls the Twin's `/project` and emits
a KPI result. That proves the orchestration spine before you add training.
