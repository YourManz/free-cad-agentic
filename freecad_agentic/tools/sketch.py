"""Sketcher operations — create sketches, add geometry, add constraints.

The Sketcher API is fiddly. We accept structured JSON for geometry and constraints
and translate to Sketcher + Part calls. Coordinates are in mm; angles in degrees.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import FreeCAD
import Part
import Sketcher

from ..transaction import transaction

_PLANES = {"XY": "XY_Plane", "XZ": "XZ_Plane", "YZ": "YZ_Plane"}


def _doc():
    doc = FreeCAD.ActiveDocument
    if doc is None:
        raise RuntimeError("no active document")
    return doc


def _resolve_body(name: Optional[str]):
    doc = _doc()
    if name:
        body = doc.getObject(name)
        if body is None or body.TypeId != "PartDesign::Body":
            raise KeyError(f"no body named {name!r}")
        return body
    for obj in doc.Objects:
        if obj.TypeId == "PartDesign::Body":
            return obj
    raise RuntimeError("no body in document; call add_body first")


def add_sketch(plane: str = "XY", body: Optional[str] = None, name: Optional[str] = None) -> Dict[str, Any]:
    doc = _doc()
    body_obj = _resolve_body(body)
    origin = body_obj.Origin
    plane_name = _PLANES.get(plane.upper())
    if plane_name is None:
        raise ValueError(f"plane must be one of {list(_PLANES)}, got {plane!r}")
    support = None
    for feat in origin.OutList:
        if feat.Name.endswith(plane_name) or getattr(feat, "Label", "") == plane_name.replace("_", " "):
            support = feat
            break
    if support is None:
        # fallback: first Plane object under origin
        for feat in origin.OutList:
            if "Plane" in feat.TypeId:
                support = feat
                break
    if support is None:
        raise RuntimeError(f"could not find {plane} datum plane on {body_obj.Name}")

    with transaction(f"add_sketch {plane}"):
        sketch = doc.addObject("Sketcher::SketchObject", name or "Sketch")
        if hasattr(sketch, "AttachmentSupport"):
            sketch.AttachmentSupport = (support, [""])
        else:
            sketch.Support = (support, [""])
        sketch.MapMode = "FlatFace"
        body_obj.addObject(sketch)
        doc.recompute()
    return {"name": sketch.Name, "body": body_obj.Name, "plane": plane.upper()}


def _add_geometry_item(sketch, item: Dict[str, Any]) -> int:
    kind = item["type"]
    if kind == "line":
        a = item["start"]
        b = item["end"]
        geo = Part.LineSegment(FreeCAD.Vector(a[0], a[1], 0), FreeCAD.Vector(b[0], b[1], 0))
    elif kind == "circle":
        c = item["center"]
        r = float(item["radius"])
        geo = Part.Circle(FreeCAD.Vector(c[0], c[1], 0), FreeCAD.Vector(0, 0, 1), r)
    elif kind == "arc":
        c = item["center"]
        r = float(item["radius"])
        start = math.radians(float(item["start_angle"]))
        end = math.radians(float(item["end_angle"]))
        circle = Part.Circle(FreeCAD.Vector(c[0], c[1], 0), FreeCAD.Vector(0, 0, 1), r)
        geo = Part.ArcOfCircle(circle, start, end)
    elif kind == "point":
        p = item["at"]
        geo = Part.Point(FreeCAD.Vector(p[0], p[1], 0))
    else:
        raise ValueError(f"unsupported geometry type: {kind!r}")
    construction = bool(item.get("construction", False))
    return sketch.addGeometry(geo, construction)


def add_sketch_geometry(sketch: str, geometry: List[Dict[str, Any]]) -> Dict[str, Any]:
    doc = _doc()
    sk = doc.getObject(sketch)
    if sk is None or sk.TypeId != "Sketcher::SketchObject":
        raise KeyError(f"no sketch named {sketch!r}")
    added: List[int] = []
    with transaction(f"add_geometry {sketch}"):
        for item in geometry:
            added.append(_add_geometry_item(sk, item))
        doc.recompute()
    return {"sketch": sketch, "added_ids": added, "geometry_count": sk.GeometryCount}


_CONSTRAINT_MAP = {
    "coincident": "Coincident",
    "horizontal": "Horizontal",
    "vertical": "Vertical",
    "parallel": "Parallel",
    "perpendicular": "Perpendicular",
    "tangent": "Tangent",
    "equal": "Equal",
    "symmetric": "Symmetric",
    "distance": "Distance",
    "distance_x": "DistanceX",
    "distance_y": "DistanceY",
    "radius": "Radius",
    "diameter": "Diameter",
    "angle": "Angle",
    "point_on_object": "PointOnObject",
}


def _make_constraint(item: Dict[str, Any]):
    kind = item["type"]
    method = _CONSTRAINT_MAP.get(kind)
    if method is None:
        raise ValueError(f"unsupported constraint type: {kind!r}")
    raw_refs = list(item.get("refs", []))
    flat: List[Any] = []
    for r in raw_refs:
        if isinstance(r, (list, tuple)):
            flat.extend(int(x) for x in r)
        else:
            flat.append(int(r))
    value = item.get("value")
    args: List[Any] = [method, *flat]
    if value is not None:
        if kind in ("angle",):
            args.append(math.radians(float(value)))
        else:
            args.append(float(value))
    return Sketcher.Constraint(*args)


def add_sketch_constraint(sketch: str, constraints: List[Dict[str, Any]]) -> Dict[str, Any]:
    doc = _doc()
    sk = doc.getObject(sketch)
    if sk is None or sk.TypeId != "Sketcher::SketchObject":
        raise KeyError(f"no sketch named {sketch!r}")
    added: List[int] = []
    with transaction(f"add_constraints {sketch}"):
        for item in constraints:
            idx = sk.addConstraint(_make_constraint(item))
            added.append(idx)
        doc.recompute()
    try:
        dof = sk.solve()
    except Exception:
        dof = None
    return {
        "sketch": sketch,
        "added_ids": added,
        "geometry_count": sk.GeometryCount,
        "constraint_count": len(sk.Constraints),
        "dof": dof,
    }


def remove_sketch_constraint(sketch: str, indices: List[int]) -> Dict[str, Any]:
    doc = _doc()
    sk = doc.getObject(sketch)
    if sk is None or sk.TypeId != "Sketcher::SketchObject":
        raise KeyError(f"no sketch named {sketch!r}")
    # Drop highest indices first so earlier indices don't shift mid-loop.
    ordered = sorted({int(i) for i in indices}, reverse=True)
    with transaction(f"remove_constraints {sketch}"):
        for idx in ordered:
            sk.delConstraint(idx)
        doc.recompute()
    try:
        dof = sk.solve()
    except Exception:
        dof = None
    return {
        "sketch": sketch,
        "removed": ordered,
        "constraint_count": len(sk.Constraints),
        "dof": dof,
    }


TOOLS = [
    (
        {
            "name": "add_sketch",
            "description": "Create a new sketch attached to a standard datum plane (XY, XZ, or YZ) of a PartDesign Body. Prefer datum planes over model faces to avoid topological-naming breakage.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "plane": {"type": "string", "enum": ["XY", "XZ", "YZ"]},
                    "body": {"type": "string", "description": "Body name; defaults to the first body in the document."},
                    "name": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        add_sketch,
    ),
    (
        {
            "name": "add_sketch_geometry",
            "description": "Add 2D geometry to a sketch. Returns the integer IDs assigned to each new piece (use them in constraints). Coordinates in mm.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sketch": {"type": "string"},
                    "geometry": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": ["line", "circle", "arc", "point"]},
                                "start": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                                "end": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                                "center": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                                "at": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                                "radius": {"type": "number"},
                                "start_angle": {"type": "number", "description": "degrees"},
                                "end_angle": {"type": "number", "description": "degrees"},
                                "construction": {"type": "boolean"},
                            },
                            "required": ["type"],
                        },
                    },
                },
                "required": ["sketch", "geometry"],
                "additionalProperties": False,
            },
        },
        add_sketch_geometry,
    ),
    (
        {
            "name": "add_sketch_constraint",
            "description": "Add one or more constraints to a sketch. refs is a list of [geo_id, point_pos] pairs or plain geo_ids. point_pos: 0=any, 1=start, 2=end, 3=center. value is mm for distances, degrees for angles.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sketch": {"type": "string"},
                    "constraints": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": list(_CONSTRAINT_MAP.keys()),
                                },
                                "refs": {"type": "array"},
                                "value": {"type": "number"},
                            },
                            "required": ["type", "refs"],
                        },
                    },
                },
                "required": ["sketch", "constraints"],
                "additionalProperties": False,
            },
        },
        add_sketch_constraint,
    ),
    (
        {
            "name": "remove_sketch_constraint",
            "description": "Delete one or more constraints from a sketch by 0-based index into sketch.Constraints. Use this to recover from over-constrained sketch errors — pass the conflicting indices reported by the solver. Returns the new constraint count and DOF.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sketch": {"type": "string"},
                    "indices": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 0},
                        "description": "0-based indices into sketch.Constraints. The error message uses 1-based indices, so subtract 1 from each.",
                    },
                },
                "required": ["sketch", "indices"],
                "additionalProperties": False,
            },
        },
        remove_sketch_constraint,
    ),
]
