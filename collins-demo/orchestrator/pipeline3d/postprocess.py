"""
postprocess.py — the delivery layer of the image→3D pipeline.

The GPU worker returns a GLB; before we serve it to the viewer we:

  1. validate_glb()  — structural check (glTF v2 binary magic, declared length,
                       JSON chunk parses) so a truncated/corrupt transfer never
                       reaches the viewer as a mysterious blank scene.
  2. mesh_stats()    — vertices / faces / watertightness / bounds via trimesh
                       (optional dep, report degrades gracefully) so the UI and
                       the agents can talk about the model's actual geometry.
  3. repair_glb()    — optional conservative cleanup (drop degenerate faces,
                       merge duplicate vertices). OFF by default: trimesh
                       re-export can disturb baked materials, so we only repair
                       when a mesh is actually broken.
"""
from __future__ import annotations

import json
import struct


def validate_glb(data: bytes) -> dict:
    """Structural GLB validation. Returns {ok, errors, json_chunk_bytes, ...}."""
    out = {"ok": False, "errors": [], "size": len(data)}
    if len(data) < 20:
        out["errors"].append("file too small to be a GLB")
        return out
    magic, version, length = struct.unpack("<III", data[:12])
    if magic != 0x46546C67:                       # 'glTF'
        out["errors"].append("not a binary glTF (bad magic)")
        return out
    if version != 2:
        out["errors"].append(f"unsupported glTF version {version}")
    if length != len(data):
        out["errors"].append(f"declared length {length} != actual {len(data)}")
    try:
        chunk_len, chunk_type = struct.unpack("<II", data[12:20])
        if chunk_type != 0x4E4F534A:              # 'JSON'
            out["errors"].append("first chunk is not JSON")
        else:
            doc = json.loads(data[20:20 + chunk_len])
            out["generator"] = doc.get("asset", {}).get("generator")
            out["meshes"] = len(doc.get("meshes", []))
            out["materials"] = len(doc.get("materials", []))
            out["images"] = len(doc.get("images", []))
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"JSON chunk unreadable: {e}")
    out["ok"] = not out["errors"]
    return out


def mesh_stats(path) -> dict:
    """Geometry statistics for the served model (best-effort, needs trimesh)."""
    try:
        import trimesh
    except Exception:
        return {"available": False}
    try:
        scene = trimesh.load(str(path), force="scene", process=False)
        geoms = list(scene.geometry.values()) if hasattr(scene, "geometry") else [scene]
        v = sum(int(g.vertices.shape[0]) for g in geoms if hasattr(g, "vertices"))
        f = sum(int(g.faces.shape[0]) for g in geoms if hasattr(g, "faces"))
        watertight = all(bool(getattr(g, "is_watertight", False)) for g in geoms) if geoms else False
        ext = None
        try:
            ext = [round(float(x), 3) for x in scene.extents]
        except Exception:
            pass
        return {"available": True, "vertices": v, "faces": f,
                "watertight": watertight, "extents": ext,
                "geometries": len(geoms)}
    except Exception as e:  # noqa: BLE001
        return {"available": True, "error": str(e)}


def repair_glb(path) -> dict:
    """Conservative in-place mesh repair (only call when validation/stats show
    real defects — re-export can disturb baked PBR materials)."""
    try:
        import trimesh
    except Exception:
        return {"repaired": False, "reason": "trimesh not installed"}
    try:
        scene = trimesh.load(str(path), force="scene")
        changed = False
        for g in scene.geometry.values():
            if not hasattr(g, "faces"):
                continue
            before = int(g.faces.shape[0])
            g.update_faces(g.nondegenerate_faces())
            g.remove_unreferenced_vertices()
            if int(g.faces.shape[0]) != before:
                changed = True
        if changed:
            scene.export(str(path))
        return {"repaired": changed}
    except Exception as e:  # noqa: BLE001
        return {"repaired": False, "reason": str(e)}
