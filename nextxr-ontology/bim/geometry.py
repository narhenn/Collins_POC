"""
bim/geometry.py — Procedural 3D building generator.

Takes a layout specification (rooms with areas, floors, equipment) and generates
a GLB file with named meshes for the BIM viewer. Each mesh is named by its
NextXR entity_id so the frontend can map clicks → entities.

Used by the scene_generator agent after Graph Writer commits a twin.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Optional

import numpy as np
import squarify
import trimesh

logger = logging.getLogger(__name__)

# Color palette by room/entity type (RGB 0-255)
TYPE_COLORS = {
    # Spatial
    "site":         [120, 120, 120],
    "building":     [100, 110, 130],
    "floor":        [80, 85, 95],
    "room":         [75, 120, 180],
    "zone":         [60, 140, 160],
    "space":        [75, 120, 180],
    # Equipment types
    "server":       [200, 60, 60],
    "mechanical":   [60, 120, 200],
    "hvac":         [60, 120, 200],
    "electrical":   [220, 170, 40],
    "power":        [220, 170, 40],
    "fire":         [220, 80, 60],
    "security":     [160, 80, 200],
    "water":        [40, 160, 200],
    "network":      [80, 200, 140],
    "office":       [80, 175, 80],
    "lobby":        [200, 160, 60],
    "storage":      [140, 130, 120],
    "default":      [100, 130, 180],
}

WALL_COLOR = [45, 50, 65, 255]
SLAB_COLOR = [55, 60, 70, 255]
EQUIPMENT_ALPHA = 200
ROOM_ALPHA = 60
WALL_THICKNESS = 0.15
WALL_HEIGHT_RATIO = 0.95  # walls slightly shorter than floor height


def _classify_entity(entity: dict) -> str:
    """Determine the type category for color coding."""
    ct = (entity.get("canonical_type") or entity.get("canonicalType") or "").lower()
    name = (entity.get("name") or entity.get("displayName") or "").lower()

    if "server" in name or "server" in ct:
        return "server"
    if "hvac" in ct or "airhandl" in ct or "chiller" in ct or "ahu" in name:
        return "hvac"
    if "ups" in ct or "transformer" in ct or "generator" in ct or "power" in ct or "electric" in ct:
        return "electrical"
    if "fire" in ct or "smoke" in ct or "alarm" in ct:
        return "fire"
    if "security" in ct or "access" in ct or "door" in ct or "camera" in ct:
        return "security"
    if "water" in ct or "tank" in ct or "pump" in ct:
        return "water"
    if "network" in ct or "edge" in ct or "switch" in ct:
        return "network"
    if "office" in name or "open plan" in name or "workspace" in name:
        return "office"
    if "lobby" in name or "reception" in name or "entry" in name:
        return "lobby"
    if "zone" in ct:
        return "zone"
    if "room" in ct or "space" in ct:
        return "room"
    if "floor" in ct or "storey" in ct:
        return "floor"
    if "building" in ct:
        return "building"
    if "site" in ct:
        return "site"
    return "default"


def _get_color(entity_type: str, alpha: int = 255) -> list:
    """Get RGBA color for an entity type."""
    rgb = TYPE_COLORS.get(entity_type, TYPE_COLORS["default"])
    return [rgb[0], rgb[1], rgb[2], alpha]


def _create_colored_box(extents, color_rgba, transform=None):
    """Create a box mesh with a uniform face color."""
    mesh = trimesh.creation.box(extents=extents)
    mesh.visual.face_colors = np.tile(color_rgba, (len(mesh.faces), 1))
    if transform is not None:
        mesh.apply_transform(transform)
    return mesh


def generate_building_glb(layout: dict, output_path: Path) -> tuple[Path, dict]:
    """Generate a GLB file from a layout specification.

    Args:
        layout: dict with keys:
            - building: {floors, footprint_w, footprint_d, floor_height}
            - rooms: [{entity_id, name, floor, target_area, type}, ...]
            - equipment: [{entity_id, name, room_entity_id, size}, ...]
        output_path: where to write the GLB

    Returns:
        (glb_path, mapping_dict) where mapping_dict is {entity_id: mesh_name}
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    bldg = layout.get("building", {})
    num_floors = max(1, bldg.get("floors", 1))
    fp_w = bldg.get("footprint_w", 30.0)
    fp_d = bldg.get("footprint_d", 20.0)
    floor_h = bldg.get("floor_height", 3.5)

    rooms = layout.get("rooms", [])
    equipment = layout.get("equipment", [])

    scene = trimesh.Scene()
    mapping = {}

    # --- Floor slabs ---
    for fi in range(num_floors):
        y = fi * floor_h
        slab = _create_colored_box(
            extents=[fp_w, 0.25, fp_d],
            color_rgba=SLAB_COLOR,
            transform=trimesh.transformations.translation_matrix([fp_w / 2, y, fp_d / 2]),
        )
        scene.add_geometry(slab, node_name=f"slab_floor_{fi}")

    # Top slab (roof)
    roof = _create_colored_box(
        extents=[fp_w, 0.25, fp_d],
        color_rgba=SLAB_COLOR,
        transform=trimesh.transformations.translation_matrix(
            [fp_w / 2, num_floors * floor_h, fp_d / 2]),
    )
    scene.add_geometry(roof, node_name="roof_slab")

    # --- Layout rooms per floor using squarify ---
    # Group rooms by floor
    floors_rooms: dict[int, list] = {}
    for r in rooms:
        fi = r.get("floor", 0)
        fi = min(fi, num_floors - 1)
        floors_rooms.setdefault(fi, []).append(r)

    # If no rooms specified, create placeholder rooms from entities
    if not rooms:
        logger.info("No rooms in layout, skipping room geometry")

    room_positions: dict[str, dict] = {}  # entity_id -> {x, y, z, dx, dy, dz, floor}

    for fi, floor_rooms in floors_rooms.items():
        areas = [max(r.get("target_area", 20), 5) for r in floor_rooms]
        if not areas:
            continue

        # squarify computes the treemap layout
        normalized = squarify.normalize_sizes(areas, fp_w - 0.5, fp_d - 0.5)
        rects = squarify.padded_squarify(normalized, 0.25, 0.25, fp_w - 0.5, fp_d - 0.5)

        y_base = fi * floor_h + 0.25  # above the slab
        wall_h = floor_h * WALL_HEIGHT_RATIO

        for i, (r, rect) in enumerate(zip(floor_rooms, rects)):
            rx, ry, rdx, rdy = rect["x"], rect["y"], rect["dx"], rect["dy"]
            entity_id = r.get("entity_id", f"room_{fi}_{i}")
            etype = r.get("type", _classify_entity(r))
            color = _get_color(etype, ROOM_ALPHA)

            # Room volume (translucent fill)
            room_mesh = _create_colored_box(
                extents=[rdx - WALL_THICKNESS * 2, wall_h * 0.5, rdy - WALL_THICKNESS * 2],
                color_rgba=color,
                transform=trimesh.transformations.translation_matrix(
                    [rx + rdx / 2, y_base + wall_h * 0.25, ry + rdy / 2]),
            )
            scene.add_geometry(room_mesh, node_name=entity_id)
            mapping[entity_id] = entity_id

            # Store position for equipment placement
            room_positions[entity_id] = {
                "x": rx, "z": ry, "dx": rdx, "dz": rdy,
                "y": y_base, "floor": fi, "wall_h": wall_h,
            }

            # Wall segments (4 walls per room)
            walls = [
                # North wall
                ([rdx, wall_h, WALL_THICKNESS],
                 [rx + rdx / 2, y_base + wall_h / 2, ry + WALL_THICKNESS / 2]),
                # South wall
                ([rdx, wall_h, WALL_THICKNESS],
                 [rx + rdx / 2, y_base + wall_h / 2, ry + rdy - WALL_THICKNESS / 2]),
                # West wall
                ([WALL_THICKNESS, wall_h, rdy],
                 [rx + WALL_THICKNESS / 2, y_base + wall_h / 2, ry + rdy / 2]),
                # East wall
                ([WALL_THICKNESS, wall_h, rdy],
                 [rx + rdx - WALL_THICKNESS / 2, y_base + wall_h / 2, ry + rdy / 2]),
            ]
            for wi, (extents, pos) in enumerate(walls):
                wall = _create_colored_box(
                    extents=extents, color_rgba=WALL_COLOR,
                    transform=trimesh.transformations.translation_matrix(pos),
                )
                scene.add_geometry(wall, node_name=f"wall_{entity_id}_{wi}")

    # --- Equipment boxes inside rooms ---
    for eq in equipment:
        entity_id = eq.get("entity_id", "")
        room_id = eq.get("room_entity_id", "")
        size = eq.get("size", [1.0, 1.2, 0.8])
        if len(size) < 3:
            size = [1.0, 1.2, 0.8]
        etype = eq.get("type", _classify_entity(eq))
        color = _get_color(etype, EQUIPMENT_ALPHA)

        # Place inside the room if we know its position
        pos = room_positions.get(room_id)
        if pos:
            # Center the equipment in the room with a small offset
            ex = pos["x"] + pos["dx"] * 0.3
            ez = pos["z"] + pos["dz"] * 0.3
            ey = pos["y"] + size[1] / 2 + 0.05
        else:
            # Fallback: place on ground floor
            eq_idx = equipment.index(eq)
            ex = 2 + (eq_idx % 5) * 3
            ez = 2 + (eq_idx // 5) * 3
            ey = 0.25 + size[1] / 2

        eq_mesh = _create_colored_box(
            extents=size, color_rgba=color,
            transform=trimesh.transformations.translation_matrix([ex, ey, ez]),
        )
        scene.add_geometry(eq_mesh, node_name=entity_id)
        mapping[entity_id] = entity_id

    # --- Outer building walls ---
    wall_h = num_floors * floor_h
    outer_walls = [
        ([fp_w, wall_h, WALL_THICKNESS], [fp_w / 2, wall_h / 2, 0]),
        ([fp_w, wall_h, WALL_THICKNESS], [fp_w / 2, wall_h / 2, fp_d]),
        ([WALL_THICKNESS, wall_h, fp_d], [0, wall_h / 2, fp_d / 2]),
        ([WALL_THICKNESS, wall_h, fp_d], [fp_w, wall_h / 2, fp_d / 2]),
    ]
    outer_color = [35, 40, 55, 180]
    for wi, (extents, pos) in enumerate(outer_walls):
        wall = _create_colored_box(
            extents=extents, color_rgba=outer_color,
            transform=trimesh.transformations.translation_matrix(pos),
        )
        scene.add_geometry(wall, node_name=f"outer_wall_{wi}")

    # Export GLB
    glb_data = scene.export(file_type="glb")
    output_path.write_bytes(glb_data)

    logger.info("Generated GLB: %d rooms, %d equipment, %d bytes",
                len(rooms), len(equipment), len(glb_data))
    return output_path, mapping


def layout_from_entities(entities: list[dict], num_floors: int = None) -> dict:
    """Create a layout specification from a list of NextXR graph entities.
    This is the deterministic fallback when no LLM is available.

    Args:
        entities: list of entity dicts with keys: id, canonicalType, displayName
        num_floors: override floor count (auto-detected if None)

    Returns:
        layout dict suitable for generate_building_glb()
    """
    locations = []
    equipment_ents = []

    for e in entities:
        ct = (e.get("canonicalType") or e.get("canonical_type") or "").lower()
        if any(k in ct for k in ("site", "building", "floor", "room", "space", "zone")):
            locations.append(e)
        else:
            equipment_ents.append(e)

    # Detect floor count from Floor entities
    floor_count = 0
    for loc in locations:
        ct = (loc.get("canonicalType") or "").lower()
        if "floor" in ct or "storey" in ct:
            floor_count += 1
    if num_floors is not None:
        floor_count = num_floors
    floor_count = max(1, floor_count if floor_count > 0 else 1)

    # Create room entries from locations (excluding site/building/floor)
    rooms = []
    for loc in locations:
        ct = (loc.get("canonicalType") or "").lower()
        if any(k in ct for k in ("site", "building", "floor")):
            continue
        eid = loc.get("id", "")
        name = loc.get("displayName", "Room")
        rooms.append({
            "entity_id": eid,
            "name": name,
            "floor": len(rooms) % floor_count,
            "target_area": 30 + len(name) * 2,  # vary area by name length
            "type": _classify_entity(loc),
        })

    # If no room-like locations, create rooms from equipment grouping
    if not rooms:
        # Group equipment by type and create rooms for them
        type_groups: dict[str, list] = {}
        for eq in equipment_ents:
            etype = _classify_entity(eq)
            type_groups.setdefault(etype, []).append(eq)

        for etype, group in type_groups.items():
            rooms.append({
                "entity_id": f"room_{etype}",
                "name": f"{etype.replace('_', ' ').title()} Room",
                "floor": len(rooms) % floor_count,
                "target_area": 20 + len(group) * 10,
                "type": etype,
            })

    # Create equipment entries
    equip_list = []
    for eq in equipment_ents:
        etype = _classify_entity(eq)
        # Find the room this equipment most likely belongs to
        best_room = None
        for r in rooms:
            if r["type"] == etype:
                best_room = r["entity_id"]
                break
        if not best_room and rooms:
            # Assign to a room on the same floor round-robin
            eq_idx = equipment_ents.index(eq)
            best_room = rooms[eq_idx % len(rooms)]["entity_id"]

        equip_list.append({
            "entity_id": eq.get("id", ""),
            "name": eq.get("displayName", "Equipment"),
            "room_entity_id": best_room,
            "type": etype,
            "size": [1.0, 1.2, 0.8],
        })

    # Building dimensions scale with room count
    total_rooms = max(1, len(rooms))
    fp_w = max(15, min(60, math.sqrt(total_rooms * 80) * 2))
    fp_d = max(12, min(40, math.sqrt(total_rooms * 80) * 1.3))

    return {
        "building": {
            "floors": floor_count,
            "footprint_w": round(fp_w, 1),
            "footprint_d": round(fp_d, 1),
            "floor_height": 3.5,
        },
        "rooms": rooms,
        "equipment": equip_list,
    }
