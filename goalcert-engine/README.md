# GoalCert Simulation Engine

A **model-driven cyber-security simulation platform**. A single operator composes an
environment (picks the assets and their controls), launches a scenario, and **watches the
engine play every actor** — Red attacks, Blue/SOC detect & respond — while outcomes
*emerge* from the modelled assets, controls and the operator's configuration. Fully
deterministic: the same inputs always produce the same timeline.

The flagship scenario, **Operation Black Phoenix**, encodes the 8-phase Red/Blue/SOC
exercise (phishing → domain-admin → exfiltration → ransomware → OT/PLC impact).

---

## How it works (five layers)

1. **Asset models** (`backend/app/engine/models/assets.py`) — each asset type (endpoint, DC,
   email, file share, ERP, MES, cloud, OT PLC, SIEM/EDR/firewall appliances…) has a state
   machine and emits characteristic telemetry when an effect hits it.
2. **Control models** (`models/controls.py`) — EDR, SIEM, firewall/IDS, segmentation, DLP,
   MFA, backups, email security. They detect and/or prevent techniques with deterministic,
   config-scaled efficacy.
3. **Technique catalog** (`catalog/techniques.py`) — MITRE-aligned attacker capabilities,
   each declaring preconditions, effects, emitted telemetry, and which controls detect/prevent it.
4. **Scenario** (`scenario.py`) — an attacker *playbook* (technique sequence) + a recommended
   environment. Expresses **intent**, not outcomes.
5. **Engine** (`run.py`) — an event-queue resolver. Detections and containments are scheduled
   into the future and interleave with later attack steps, so **blue containment can truncate
   the attack** (emergent). Produces a full timeline + scores + KPIs (MTTD/MTTR/detection rate).

Adding a new scenario = a new playbook reusing the catalog. Adding a new asset/control/technique
= one model in the catalog. No engine changes.

---

## Run it — local dev (fastest, zero infra)

The backend defaults to a local **SQLite** DB and seeds itself on startup.

**Backend** (Python 3.11+, [uv](https://docs.astral.sh/uv/)):
```bash
cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload --port 8000
```

**Frontend** (Node 20+):
```bash
cd frontend
npm install
npm run dev
```
Open **http://localhost:5173** (Vite proxies `/api` and `/ws` to the backend on :8000).

## Run it — Docker (Postgres-backed)
```bash
docker compose up --build
```
Then open **http://localhost:8080** (web → nginx → api → Postgres).

---

## Try the headline demo

1. **Library → Operation Black Phoenix** → opens *Configure & Launch*.
2. **Select assets** for the environment and **toggle controls** (EDR / SIEM / segmentation /
   DLP / MFA / backups / email security); set **difficulty** and **team readiness**.
3. **Launch** → the *Active Simulation* streams live: phase tracker, console telemetry, a
   network map whose nodes change state, an alert feed, and operator controls
   (pause / resume / speed / manual inject).
4. On completion, open the **After-Action Report** (exec summary, attack timeline, MITRE map,
   scorecard, regulatory & financial impact, recommendations, maturity score, corrective actions).

**See emergence:** run it once at **Easy** with all controls on (the kill-chain collapses at
phishing), then again at **Expert** with controls off (full ransomware + OT impact). Same engine,
different posture → deterministically different outcome.

---

## Tests
```bash
cd backend
uv run pytest -q
```
Covers engine determinism, full 8-phase coverage, strong-vs-weak **emergence**, asset-selection
impact (removing SIEM degrades detection), the disable-EDR-cancels-alerts behaviour, and the
REST + WebSocket API end-to-end.

---

## Layout
```
backend/app/
  engine/        # pure deterministic simulation core (no web/db deps)
    models/      # asset & control behaviour models + registries
    catalog/     # technique specs + registry
    resolve/     # preconditions, resolution, detection, response (swappable seams)
    run.py       # the event-queue orchestrator
  scenarios/     # playbook authoring + Operation Black Phoenix
  services/      # compute/persist runs + live streaming RunManager
  reports/       # deterministic AAR generator
  db/ api/ ws/   # persistence, REST routers, WebSocket
frontend/src/    # React + TS UI (dashboard, library, launch+asset-selection, active sim,
                 # builder, leaderboard, reports)
```

## Notes & roadmap
- **Deterministic, no AI** by design; the resolver interfaces in `engine/resolve/` are seams for
  a future `AIResolver` / real-tool adapters (SIEM/EDR), and a `seed` field reserves a future
  stochastic mode.
- Schema is created via `create_all` for the POC; swap in Alembic migrations for production.
- No auth yet (single-operator POC) — a token-auth seam can wrap the routers later.
