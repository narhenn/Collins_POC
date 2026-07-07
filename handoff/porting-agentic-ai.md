# Porting Guide — Agentic AI Platform

**Your role:** own every LLM agent and workflow. You read the twin's state through the
Digital Twin API, reason, and return diagnoses, plans, narratives and answers. You never
simulate physics yourself — you *reason over* what the twin reports.

**This is the highest-value port** — the agents are the most wrongly-placed capability in
the demo. They currently sit as ~30 plain Python functions; on your platform they become
real, persisted, memory-backed agents.

---

## 1. Your source of truth in the reference

| Reference file | What it is |
|---|---|
| `collins-demo/orchestrator/claude_client.py` | **the mother lode** — ~30 agent functions with their exact prompts, system messages, response schemas, and token budgets. This is what you copy *behaviour* from. |
| `collins-demo/orchestrator/routes.py` (`/agents/*`) | the endpoints the UI calls today — your de-facto capability list |
| `collins-demo/web/src/aiStubs.js` | the zero-token *fallback* generators — port these too, they're your resilience/cost-control mode |
| `collins-demo/web/src/{Intelligence,Scenario,Trainer,Chat}.jsx` | how the agents are consumed in the UI — shows the expected inputs/outputs |

### The agent inventory to port (from `claude_client.py`)

| Capability | Function(s) | Input it needs | Output shape |
|---|---|---|---|
| diagnose | `diagnosis_agent`, `diagnose_snapshot` | diagnostics/telemetry | narrative (markdown) |
| analyze | `analysis_agent`, `analyze_projection` | diagnostics + prediction | narrative |
| narrate | `narrate_sensors`, co-pilot loop | live state snapshot | short observation |
| work-order | `generate_work_order` | diagnostics | structured steps (Pydantic) |
| procedure | `build_procedure` | domain + fault | structured steps w/ safety/deps |
| cascade | `cascade_analysis` | diagnostics + prediction | failure-chain narrative |
| alert | `predictive_alert` | prediction | short alert or null |
| procurement | `parts_procurement_agent` | work order | parts list (Pydantic) |
| incident-report | `generate_incident_report` | findings + diagnostics | report |
| asset-status | `asset_status` | one component | per-component status |
| troubleshoot | `troubleshoot_chat` | history + message | chat reply |
| dashboard-chat | `dashboard_chat` | snapshot + message | chat reply |
| build-a-twin | `vision_to_twin_spec`, `build_twin_reply` | image/description | twin spec / chat |
| (shared w/ Scenario) | `author_sim` | NL + fault catalogue | scenario spec — **owned by Scenario Engine, hosted logic here if you expose author** |

## 2. Build ON your existing patterns — the whole point of the port

Your platform (`automind-engine/backend/app/`) already has what the demo faked:
- `engine/executor.py`, `engine/graph.py`, `engine/nodes/` (`ai_action`, `decision`,
  `integration`, `web_search`, `code_exec`, …) — a **real workflow engine**.
- `models/` — DB-backed `Agent`, `Execution`, `Memory`, `Template`.
- `routers/` — `agents`, `workflows`, `executions`, `chat`, `memory`, `templates`.

**So each demo function becomes an Agent/workflow, not a copied function:**
- The **prompt + system message** from `claude_client.py` → the `ai_action` node's config.
- **Fetching twin context** (the demo passes `diagnostics`/`latest` dicts as args) → an
  `integration` node that calls the Digital Twin API (`GET /twins/{tenant}/diagnostics`).
- The **Pydantic response schema** (e.g. `WorkOrder`, `ProcurementList`) → your agent's
  structured-output schema.
- **Chat history** (`troubleshoot_chat`, `dashboard_chat` take a `history` list) → your
  `Memory` model, keyed by `thread_id`.

Seed these as **templates** so they're reproducible, and let `agents/generate` (which
already exists) create instances.

## 3. Expose a stable facade for the hub

Your native API is `POST /agents/{id}/execute`. The hub shouldn't need to know agent ids.
Add a thin **capability facade** on top:

```
POST /api/v1/agents/run  {capability, tenant, context}  -> {result}
POST /api/v1/agents/chat {thread_id, message, context}  -> {reply}
GET  /api/v1/agents/capabilities                        -> [{capability, needs}]
```

`run` maps `capability` → the right agent/workflow, pulls twin context via the
integration node if `context` isn't fully supplied, executes, and returns the result.
Internally it's your executor; externally it's one stable verb per capability. This
matches the **Agentic AI** block in [README.md](README.md#agentic-ai--apiv1agents).

## 4. Keep the fallback mode

Port `aiStubs.js` into a server-side **stub provider** selectable per request/tenant
(`mode: stub|agent`). In stub mode you return the deterministic local generation with
zero LLM calls. The demo relies on this for cost control and offline resilience — keep it.

## 5. Do NOT copy these demo shortcuts

- **Direct Anthropic calls inside request handlers.** That's the demo bypassing you.
  Route every model call through your executor/nodes so you get retries, logging,
  memory, and model-config in one place.
- **Passing giant context dicts as function args.** Replace with an integration node that
  *fetches* twin context — so agents stay decoupled from whoever calls them.
- **Prompts inline in code.** Move them into template/agent config so non-engineers can
  tune them (that's a big reason your platform exists).
- **Losing the token budgets.** `claude_client.py` sets deliberate `max_tokens` per agent
  (e.g. 8000 for procedures to avoid truncation) — carry those over.

## 6. Acceptance criteria

- [ ] `POST /agents/run {capability:"diagnose", tenant}` returns the same quality diagnosis as the demo, but as a persisted `Execution`.
- [ ] `work-order` and `procurement` return valid structured output matching the demo's Pydantic schemas.
- [ ] `POST /agents/chat` threads memory across turns (troubleshoot/dashboard chat).
- [ ] Each capability works for **any** domain (EDM, turbine, tram) — the demo's agents are already domain-generic; keep that.
- [ ] `mode:"stub"` returns instantly with no LLM call.
- [ ] Prompts live in templates/config, not hard-coded in handlers.

**Recommended first PR:** port three capabilities end-to-end (`diagnose`, `work-order`,
`dashboard-chat`) through your executor + the `/agents/run` facade, pulling context from
the Digital Twin API. Prove the pattern, then batch the rest.
