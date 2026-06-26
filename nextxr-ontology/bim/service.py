"""
bim/service.py — IFC parsing, entity import, and geometry conversion.

Parses IFC files with ifcopenshell, maps IFC types to NextXR ontology classes,
creates entities via GraphWriter (the single validated write path), and converts
geometry to GLB for the frontend 3D viewer.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import ifcopenshell
import ifcopenshell.util.element as element_util

logger = logging.getLogger(__name__)

CORE = "https://ontology.nextxr.io/v3/core#"
CFP = "https://ontology.nextxr.io/v3/cfp#"

# IFC entity type -> NextXR canonical_type IRI
IFC_TYPE_MAP = {
    # Spatial
    "IfcSite":              CORE + "Site",
    "IfcBuilding":          CFP + "Building",
    "IfcBuildingStorey":    CFP + "Floor",
    "IfcSpace":             CFP + "Room",
    "IfcZone":              CFP + "Zone",
    # HVAC
    "IfcUnitaryEquipment":  CFP + "AirHandlingUnit",
    "IfcAirTerminal":       CFP + "AirHandlingUnit",
    "IfcChiller":           CFP + "Chiller",
    "IfcBoiler":            CFP + "Boiler",
    "IfcCoolingTower":      CFP + "CoolingTower",
    "IfcCoil":              CFP + "AirHandlingUnit",
    "IfcFan":               CFP + "AirHandlingUnit",
    "IfcFilter":            CFP + "AirFilter",
    "IfcHumidifier":        CFP + "AirHandlingUnit",
    # Electrical
    "IfcTransformer":       CFP + "Transformer",
    "IfcSwitchingDevice":   CFP + "Switchgear",
    "IfcElectricGenerator": CFP + "Generator",
    "IfcElectricMotor":     CFP + "Generator",
    # Plumbing / water
    "IfcPump":              CFP + "Pump",
    "IfcValve":             CFP + "Valve",
    "IfcTank":              CFP + "WaterTank",
    "IfcPipeFitting":       CFP + "Pump",
    # Fire
    "IfcFireSuppressionTerminal": CFP + "SuppressionSystem",
    "IfcAlarm":             CFP + "FireAlarmPanel",
    # Transport
    "IfcTransportElement":  CFP + "Elevator",
    # Sensors
    "IfcSensor":            CFP + "TemperatureSensor",
    "IfcActuator":          CFP + "Switchgear",
    # Security
    "IfcDoor":              CFP + "AccessDoor",
}

# IFC types to skip (structural / non-operational)
_SKIP_TYPES = frozenset({
    "IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcColumn", "IfcBeam",
    "IfcRoof", "IfcCovering", "IfcCurtainWall", "IfcPlate",
    "IfcRailing", "IfcStair", "IfcStairFlight", "IfcRamp", "IfcRampFlight",
    "IfcWindow", "IfcOpeningElement", "IfcFurnishingElement",
    "IfcBuildingElementProxy", "IfcMember", "IfcFooting",
})


def _ifc_name(element) -> str:
    """Get a display name for an IFC element."""
    name = getattr(element, "Name", None) or getattr(element, "LongName", None)
    if name:
        return str(name)
    return f"{element.is_a()}-{element.GlobalId[:8]}"


def _extract_props(element) -> dict:
    """Extract useful properties from an IFC element."""
    props = {}
    try:
        psets = element_util.get_psets(element)
        for pset_name, pset_vals in psets.items():
            for k, v in pset_vals.items():
                if v is not None and k != "id" and isinstance(v, (str, int, float, bool)):
                    props[k] = v
    except Exception:
        pass
    return props


class BimImporter:
    """Parse IFC files and import entities into the NextXR graph."""

    def __init__(self, writer):
        self.writer = writer

    def parse_ifc(self, ifc_path: Path) -> dict:
        """Parse an IFC file and return the spatial hierarchy as a tree."""
        model = ifcopenshell.open(str(ifc_path))
        tree = {"elements": [], "stats": {"total": 0, "imported": 0, "skipped": 0}}

        # Walk spatial hierarchy: Project -> Site -> Building -> Storey -> Space
        sites = model.by_type("IfcSite")
        for site in sites:
            tree["elements"].append(self._walk_element(site, model, tree["stats"]))

        # If no sites, try buildings directly
        if not sites:
            buildings = model.by_type("IfcBuilding")
            for bldg in buildings:
                tree["elements"].append(self._walk_element(bldg, model, tree["stats"]))

        return tree

    def _walk_element(self, element, model, stats) -> dict:
        """Recursively walk an IFC element and its children."""
        ifc_type = element.is_a()
        global_id = element.GlobalId
        name = _ifc_name(element)
        mapped_type = IFC_TYPE_MAP.get(ifc_type)

        node = {
            "ifc_type": ifc_type,
            "ifc_global_id": global_id,
            "name": name,
            "canonical_type": mapped_type,
            "properties": _extract_props(element),
            "children": [],
            "contained": [],
        }
        stats["total"] += 1
        if mapped_type:
            stats["imported"] += 1

        # Spatial decomposition (IfcRelAggregates)
        if hasattr(element, "IsDecomposedBy"):
            for rel in element.IsDecomposedBy:
                for child in rel.RelatedObjects:
                    node["children"].append(self._walk_element(child, model, stats))

        # Contained elements (IfcRelContainedInSpatialStructure)
        if hasattr(element, "ContainsElements"):
            for rel in element.ContainsElements:
                for child in rel.RelatedElements:
                    child_type = child.is_a()
                    if child_type in _SKIP_TYPES:
                        stats["skipped"] += 1
                        continue
                    node["contained"].append(self._walk_element(child, model, stats))

        return node

    def import_entities(self, tenant_id: str, tree: dict, actor: str = "bim-importer") -> dict:
        """Walk the parsed tree and create entities via GraphWriter.
        Returns {ifc_global_id -> nxr_entity_id} mapping."""
        from graph.writer import Rel

        mapping = {}
        for element in tree["elements"]:
            self._import_node(tenant_id, element, None, actor, mapping, Rel)
        return mapping

    def _import_node(self, tenant_id, node, parent_id, actor, mapping, Rel):
        """Recursively import a node and its children."""
        canonical_type = node.get("canonical_type")
        if not canonical_type:
            # Still walk children even if this node is unmapped
            for child in node.get("children", []):
                self._import_node(tenant_id, child, parent_id, actor, mapping, Rel)
            for child in node.get("contained", []):
                self._import_node(tenant_id, child, parent_id, actor, mapping, Rel)
            return

        props = {"displayName": node["name"], "bimGlobalId": node["ifc_global_id"]}
        # Add floor level index for storeys
        if node["ifc_type"] == "IfcBuildingStorey":
            elev = node["properties"].get("Elevation")
            if elev is not None:
                try:
                    props["levelIndex"] = int(float(elev))
                except (ValueError, TypeError):
                    pass

        # Set a default status for equipment
        if canonical_type not in (CORE + "Site", CFP + "Building", CFP + "Floor",
                                   CFP + "Room", CFP + "Zone"):
            props["status"] = "running"

        # Build relationships
        rels = []
        if parent_id:
            rels.append(Rel("nxr:locatedAt", parent_id))

        result = self.writer.create(
            tenant_id=tenant_id,
            canonical_type=canonical_type,
            actor=actor,
            properties=props,
            relationships=rels if rels else None,
        )

        entity_id = None
        if result.ok:
            entity_id = result.node_id
            mapping[node["ifc_global_id"]] = entity_id
        else:
            logger.warning("BIM import: failed to create %s (%s): %s",
                           node["name"], canonical_type.split("#")[-1], result.error)

        # Import children with this entity as parent
        next_parent = entity_id or parent_id
        for child in node.get("children", []):
            self._import_node(tenant_id, child, next_parent, actor, mapping, Rel)
        for child in node.get("contained", []):
            self._import_node(tenant_id, child, next_parent, actor, mapping, Rel)

    def convert_geometry(self, ifc_path: Path, output_dir: Path) -> Optional[Path]:
        """Convert IFC geometry to GLB format.
        Tries IfcConvert CLI first, falls back to Python ifcopenshell.geom."""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_glb = output_dir / "model.glb"

        # Try IfcConvert CLI (fastest, most reliable)
        ifc_convert = shutil.which("IfcConvert") or shutil.which("ifcconvert")
        if ifc_convert:
            try:
                subprocess.run(
                    [ifc_convert, str(ifc_path), str(output_glb),
                     "--use-element-guids", "--weld-vertices"],
                    check=True, capture_output=True, timeout=300,
                )
                if output_glb.exists():
                    return output_glb
            except Exception as e:
                logger.warning("IfcConvert CLI failed, falling back to Python: %s", e)

        # Fallback: Python-based conversion via ifcopenshell.geom
        return self._convert_geometry_python(ifc_path, output_glb)

    def _convert_geometry_python(self, ifc_path: Path, output_glb: Path) -> Optional[Path]:
        """Convert IFC to GLB using ifcopenshell.geom Python API."""
        try:
            import ifcopenshell.geom

            model = ifcopenshell.open(str(ifc_path))
            geom_settings = ifcopenshell.geom.settings()
            geom_settings.set(geom_settings.USE_WORLD_COORDS, True)
            ser_settings = ifcopenshell.geom.serializer_settings()

            sr = ifcopenshell.geom.serializers.gltf(
                str(output_glb), geom_settings, ser_settings)
            sr.writeHeader()
            count = 0
            for elem in ifcopenshell.geom.iterate(
                geom_settings, model,
                exclude=("IfcOpeningElement",),
            ):
                sr.write(elem)
                count += 1
            sr.finalize()
            if output_glb.exists() and output_glb.stat().st_size > 0:
                logger.info("GLB conversion: %d elements -> %s", count, output_glb)
                return output_glb
            return None
        except Exception as e:
            logger.error("Python geometry conversion failed: %s", e)
            return None


def get_bim_dir(tenant_id: str) -> Path:
    """Return the BIM data directory for a tenant."""
    base = Path(__file__).resolve().parent.parent / "data" / "bim" / tenant_id
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_bim_status(tenant_id: str) -> dict:
    """Check if a BIM model exists for a tenant."""
    bim_dir = get_bim_dir(tenant_id)
    glb = bim_dir / "model.glb"
    mapping_file = bim_dir / "mapping.json"
    if glb.exists() and mapping_file.exists():
        mapping = json.loads(mapping_file.read_text())
        mtime = datetime.fromtimestamp(glb.stat().st_mtime, tz=timezone.utc)
        return {
            "has_model": True,
            "entity_count": len(mapping),
            "imported_at": mtime.isoformat(),
            "glb_size_mb": round(glb.stat().st_size / (1024 * 1024), 2),
        }
    return {"has_model": False, "entity_count": 0, "imported_at": None}
