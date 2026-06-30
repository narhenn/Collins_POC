"""
main.py — the Collins agentic-demo orchestrator (BFF).

Run from the repo-root venv:
    .venv\\Scripts\\python.exe -m uvicorn main:app --port 8090   (from collins-demo/orchestrator)

It serves the thin /api the web app uses and fans out to the three platforms.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import config
from routes import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orchestrator")

app = FastAPI(title="Collins Agentic Twin — Orchestrator", version="1.0.0")

# The web app (Vite dev server on :5174) calls us cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(httpx.HTTPError)
async def _platform_unreachable(request: Request, exc: httpx.HTTPError):
    """Turn a failed call to a platform (NextXR/GoalCert/AUTOMIND) into a clear
    503 instead of an opaque 500 — almost always means the backend stack isn't
    up. Start it first with start.ps1 (Neo4j + NextXR on :8000)."""
    logger.warning("platform call failed on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": ("A platform service is unreachable. Bring the backend up "
                       "first: run start.ps1 (Neo4j + NextXR on :8000), then "
                       "demo.ps1 — the web app talks only to the orchestrator."),
            "where": request.url.path,
            "error": str(exc),
        },
    )


app.include_router(router)


@app.on_event("startup")
def _startup():
    import tripo
    logging.getLogger("orchestrator").info(
        "Tripo: %s", "enabled" if config.tripo_enabled else "no key set")
    if config.tripo_enabled:
        tripo.log_balance("startup")


@app.get("/")
def root():
    return {"service": "collins-orchestrator",
            "platforms": {"nextxr": config.NEXTXR_URL,
                          "automind": config.AUTOMIND_URL,
                          "goalcert": config.GOALCERT_URL},
            "claude_model": config.CLAUDE_MODEL}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, reload=False)
