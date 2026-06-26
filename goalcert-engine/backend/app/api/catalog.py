"""Catalog endpoints — the reusable building blocks (served live from code registries)."""
from __future__ import annotations

from fastapi import APIRouter

from app.engine.catalog import spec
from app.engine.models import assets, controls

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/assets")
def asset_catalog() -> list[dict]:
    return assets.catalog()


@router.get("/controls")
def control_catalog() -> list[dict]:
    return controls.catalog()


@router.get("/techniques")
def technique_catalog() -> list[dict]:
    return spec.catalog()
