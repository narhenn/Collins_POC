"""FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.engine  # noqa: F401  (populate asset/control/technique registries)
from app.api import catalog, dashboard, runs, scenarios
from app.core.settings import settings
from app.db.base import init_db
from app.ws import runs as ws_runs


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="GoalCert Simulation Engine", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog.router)
app.include_router(scenarios.router)
app.include_router(runs.router)
app.include_router(dashboard.router)
app.include_router(ws_runs.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "goalcert-engine"}
