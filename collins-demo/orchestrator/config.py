"""
config.py — central configuration for the Collins agentic-demo orchestrator.

Everything is read from the environment (a .env next to this file is loaded
automatically). The orchestrator is the ONLY component that holds secrets and
the platform base URLs — the web app only ever talks to the orchestrator.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load collins-demo/orchestrator/.env if present.
load_dotenv(Path(__file__).resolve().parent / ".env")


class Config:
    # ── Claude (Anthropic) ──
    ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
    # Default to the latest, most capable model. Override with CLAUDE_MODEL
    # (e.g. claude-sonnet-4-6) for faster/cheaper demo runs.
    CLAUDE_MODEL: str = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")

    # ── The three platforms (host ports published by docker compose) ──
    NEXTXR_URL: str = os.environ.get("NEXTXR_URL", "http://localhost:8000")
    AUTOMIND_URL: str = os.environ.get("AUTOMIND_URL", "http://localhost:8001")
    GOALCERT_URL: str = os.environ.get("GOALCERT_URL", "http://localhost:8002")

    # ── AUTOMIND auth (seed demo user, override as needed) ──
    AUTOMIND_EMAIL: str = os.environ.get("AUTOMIND_EMAIL", "prem@goalcert.com")
    AUTOMIND_PASSWORD: str = os.environ.get("AUTOMIND_PASSWORD", "demo1234")

    # ── Tripo (2D -> 3D generation) ──
    TRIPO_API_KEY: str = os.environ.get("TRIPO_API_KEY", "")
    TRIPO_BASE: str = os.environ.get("TRIPO_BASE", "https://api.tripo3d.ai/v2/openapi")

    # ── Server ──
    PORT: int = int(os.environ.get("ORCHESTRATOR_PORT", "8090"))

    @property
    def claude_enabled(self) -> bool:
        return bool(self.ANTHROPIC_API_KEY)

    @property
    def tripo_enabled(self) -> bool:
        return bool(self.TRIPO_API_KEY)


config = Config()
