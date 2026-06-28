# Running the Collins Aerospace PoC

Two moving parts, started independently:

1. **Backend** — runs entirely in **Docker** (NextXR Digital Twin + AUTOMIND + GoalCert + databases).
   You never run `python -m server.main` by hand.
2. **Frontend** — runs **separately** as a Vite dev server, proxying API calls to the backend.

## TL;DR

```powershell
./start.ps1                    # 1. brings the WHOLE backend up in Docker, waits until it's healthy
cd frontend ; npm run dev      # 2. (new window) starts the UI at http://localhost:5173
```

Open **http://localhost:5173**.

---

## What `start.ps1` does

Self-healing backend launcher. It starts Docker Desktop if it isn't running, then
`docker compose --profile full up -d` to bring up every backend service:

| Service          | Port            | Role                                            |
|------------------|-----------------|-------------------------------------------------|
| Neo4j            | 7474 / 7687     | NextXR graph store                              |
| Redis            | 6379            | NextXR event bus                                |
| Postgres         | 5433            | AUTOMIND database                               |
| Redis-AM         | 6380            | AUTOMIND Celery broker                          |
| **NextXR API**   | **8000**        | **Digital Twin backend — the frontend talks here** |
| AUTOMIND         | 8001            | Workflow engine (integrated via NextXR)         |
| GoalCert         | 8002            | Simulation engine (integrated via NextXR)       |

It then waits for `GET /api/v1/health` on :8000 to return 200 before reporting ready.

Flags:

```powershell
./start.ps1            # full backend stack in Docker (default)
./start.ps1 -Build     # force a clean rebuild of all images
./start.ps1 -Infra     # databases only — for running NextXR from the venv
./start.ps1 -Local     # DBs + AUTOMIND + GoalCert in Docker, NextXR from the local venv (live code)
./start.ps1 -Down      # stop and remove all containers
```

## Running the frontend

```powershell
cd frontend
npm install     # first time only
npm run dev     # Vite dev server (hot-reload) → http://localhost:5173
```

The dev server (`vite.config.js`) proxies `/api` and the SSE event stream to the
backend on :8000, so the UI works against the dockerized backend with no extra config.

---

## How the three products are wired together

The **NextXR Digital Twin** backend is the hub. It integrates the other two:

- **AUTOMIND** (workflow engine) and **GoalCert** (simulation engine) are called over
  HTTP from `nextxr-ontology/server/integration_clients.py`, exposed to the UI through
  `nextxr-ontology/server/integration_routes.py` (`/api/v1/integration/...`).
- The frontend reaches them through the same `/api/v1` surface (`frontend/src/api/client.js`),
  used by the **Live Ops** panel and the 18-step workflow pipeline view.
- In Docker, NextXR finds them via `AUTOMIND_URL=http://automind:8001` and
  `GOALCERT_URL=http://goalcert:8002` (set in `docker-compose.yml`). Each integration is
  best-effort: if AUTOMIND or GoalCert is down, NextXR degrades gracefully instead of failing.

---

## Local development of the NextXR backend (optional)

If you want to edit NextXR Python code and see it live (instead of rebuilding the image),
run the databases + the other two engines in Docker and NextXR from the venv:

```powershell
# one-time: create the venv
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

./start.ps1 -Local     # DBs + AUTOMIND + GoalCert in Docker, NextXR from .venv on :8000
cd frontend ; npm run dev   # UI in another window
```

`-Local` sets the env vars NextXR needs (`NEO4J_URI`, `NXR_REDIS_URL`, `AUTOMIND_URL`,
`GOALCERT_URL`) to point at the dockerized services on localhost.

---

## Health check

```powershell
curl http://localhost:8000/api/v1/health
```

- `{"status":"healthy", ...}`  → all good, live data flowing
- `{"status":"degraded", ...}` → backend up, Neo4j still warming up (try again shortly)
- connection refused           → backend isn't up; run `./start.ps1`

## Common gotchas

- **Stale image / old UI in the container:** rebuild with `./start.ps1 -Build`.
- **Port 8000 busy from a local run:** `./start.ps1 -Down`, or kill the local `python` on :8000.
- **Docker engine wedged** (`docker ps` returns a 500): open Docker Desktop, wait for the
  whale icon to settle, then re-run. `wsl --shutdown` + reopen Docker as a last resort.
- **Logs:** `docker compose --profile full logs -f server` (or `automind`, `goalcert`).
