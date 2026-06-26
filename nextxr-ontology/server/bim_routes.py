"""
bim_routes.py — BIM/IFC upload, import, and model serving.

  POST   /api/v1/bim/upload?tenant=X   upload IFC file, import entities, convert geometry
  GET    /api/v1/bim/{tenant}/model.glb serve the converted GLB file
  GET    /api/v1/bim/{tenant}/mapping   IFC GlobalId -> NextXR entity ID mapping
  GET    /api/v1/bim/{tenant}/status    check if BIM model exists
  DELETE /api/v1/bim/{tenant}           remove BIM model files
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from graph.writer import GraphWriter
from changelog.service import ChangeLog
from bim.service import BimImporter, get_bim_dir, get_bim_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/bim", tags=["bim"])


@router.post("/upload")
async def upload_bim(tenant: str, file: UploadFile = File(...)):
    """Upload an IFC file: parse spatial hierarchy, import entities via
    GraphWriter, convert geometry to GLB for the 3D viewer."""
    if not tenant:
        raise HTTPException(400, "tenant query parameter required")

    if not file.filename or not file.filename.lower().endswith(".ifc"):
        raise HTTPException(400, "Only .ifc files are supported")

    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        writer = GraphWriter(changelog=ChangeLog())
        importer = BimImporter(writer)

        # Parse IFC spatial hierarchy
        tree = importer.parse_ifc(tmp_path)

        # Import entities into Neo4j graph via GraphWriter
        mapping = importer.import_entities(tenant, tree, actor="bim-importer")

        # Convert geometry to GLB
        bim_dir = get_bim_dir(tenant)
        glb_path = importer.convert_geometry(tmp_path, bim_dir)

        # Save the mapping
        mapping_file = bim_dir / "mapping.json"
        mapping_file.write_text(json.dumps(mapping, indent=2))

        return {
            "status": "imported",
            "filename": file.filename,
            "entity_count": len(mapping),
            "stats": tree["stats"],
            "has_geometry": glb_path is not None,
            "glb_url": f"/api/v1/bim/{tenant}/model.glb" if glb_path else None,
        }
    except Exception as e:
        logger.error("BIM upload failed: %s", e)
        raise HTTPException(500, f"BIM import failed: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/{tenant}/model.glb")
def serve_model(tenant: str):
    """Serve the converted GLB file for the 3D viewer."""
    glb = get_bim_dir(tenant) / "model.glb"
    if not glb.exists():
        raise HTTPException(404, f"No BIM model for tenant '{tenant}'")
    return FileResponse(glb, media_type="model/gltf-binary", filename="model.glb")


@router.get("/{tenant}/mapping")
def get_mapping(tenant: str):
    """Return the IFC GlobalId -> NextXR entity ID mapping."""
    mapping_file = get_bim_dir(tenant) / "mapping.json"
    if not mapping_file.exists():
        raise HTTPException(404, f"No BIM mapping for tenant '{tenant}'")
    return json.loads(mapping_file.read_text())


@router.get("/{tenant}/status")
def bim_status(tenant: str):
    """Check if a BIM model exists for this tenant."""
    return get_bim_status(tenant)


@router.delete("/{tenant}")
def delete_bim(tenant: str):
    """Remove BIM model files (GLB + mapping). Does NOT delete graph entities."""
    bim_dir = get_bim_dir(tenant)
    removed = []
    for f in ("model.glb", "mapping.json"):
        fp = bim_dir / f
        if fp.exists():
            fp.unlink()
            removed.append(f)
    return {"status": "deleted", "removed": removed}
