from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db
from app.routers import auth, agents, workflows, templates, dashboard, executions, integrations, memory, chat

# Import models so they are registered with Base.metadata before init_db
import app.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="AUTOMIND API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) if settings.DEBUG else "Internal server error"},
    )


app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(workflows.router)
app.include_router(templates.router)
app.include_router(dashboard.router)
app.include_router(executions.router)
app.include_router(integrations.router)
app.include_router(memory.router)
app.include_router(chat.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "automind-api"}
