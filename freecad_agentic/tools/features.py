"""PartDesign features: pad, pocket, hole, fillet, chamfer, revolution."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import FreeCAD

from ..transaction import transaction


def _doc():
    doc = FreeCAD.ActiveDocument
    if doc is None:
        raise RuntimeError("no active document")
    return doc


def _body_of(sketch):
    for obj in sketch.InList:
        if obj.TypeId == "PartDesign::Body":
            return obj
    raise RuntimeError(f"sketch {sketch.Name} is not inside any body")


def _resolve_sketch(name: str):
    doc = _doc()
    sk = doc.getObject(name)
    if sk is None or sk.TypeId != "Sketcher::SketchObject":
        raise KeyError(f"no sketch named {name!r}")
    return doc, sk, _body_of(sk)


def add_pad(sketch: str, length: float, direction: str = "normal", length2: Optional[float] = None, reversed_: bool = False) -> Dict[str, Any]:
    doc, sk, body = _resolve_sketch(sketch)
    with transaction(f"pad {sketch}"):
        pad = doc.addObject("PartDesign::Pad", "Pad")
        body.addObject(pad)
        pad.Profile = sk
        pad.Length = float(length)
        if direction == "symmetric":
            pad.Midplane = True
        elif direction == "two_length" and length2 is not None:
            pad.Type = 4  # TwoLengths
            pad.Length2 = float(length2)
        pad.Reversed = bool(reversed_)
        sk.Visibility = False
        doc.recompute()
    return {"name": pad.Name, "sketch": sk.Name, "length": float(length)}


def add_pocket(sketch: str, depth: float, through_all: bool = False) -> Dict[str, Any]:
    doc, sk, body = _resolve_sketch(sketch)
    with transaction(f"pocket {sketch}"):
        pocket = doc.addObject("PartDesign::Pocket", "Pocket")
        body.addObject(pocket)
        pocket.Profile = sk
        if through_all:
            pocket.Type = 1  # ThroughAll
        else:
            pocket.Length = float(depth)
        sk.Visibility = False
        doc.recompute()
    return {"name": pocket.Name, "sketch": sk.Name}


def add_hole(sketch: str, diameter: float, depth: Optional[float] = None, through_all: bool = False, counterbore_diameter: Optional[float] = None, counterbore_depth: Optional[float] = None) -> Dict[str, Any]:
    doc, sk, body = _resolve_sketch(sketch)
    with transaction(f"hole {sketch}"):
        hole = doc.addObject("PartDesign::Hole", "Hole")
        body.addObject(hole)
        hole.Profile = sk
        hole.Diameter = float(diameter)
        if through_all:
            hole.DepthType = "ThroughAll"
        elif depth is not None:
            hole.DepthType = "Dimension"
            hole.Depth = float(depth)
        if counterbore_diameter is not None:
            hole.HoleCutType = "Counterbore"
            hole.HoleCutDiameter = float(counterbore_diameter)
            if counterbore_depth is not None:
                hole.HoleCutDepth = float(counterbore_depth)
        sk.Visibility = False
        doc.recompute()
    return {"name": hole.Name, "sketch": sk.Name}


def add_fillet(edges: List[str], radius: float) -> Dict[str, Any]:
    """edges is a list of 'ObjectName.EdgeN' strings, e.g. 'Pad.Edge3'."""
    doc = _doc()
    if not edges:
        raise ValueError("edges must not be empty")
    first_obj_name = edges[0].split(".")[0]
    base = doc.getObject(first_obj_name)
    if base is None:
        raise KeyError(f"no object named {first_obj_name!r}")
    body = _body_of(base) if base.TypeId != "PartDesign::Body" else base
    with transaction("fillet"):
        fillet = doc.addObject("PartDesign::Fillet", "Fillet")
        body.addObject(fillet)
        fillet.Base = (base, [e.split(".", 1)[1] for e in edges])
        fillet.Radius = float(radius)
        doc.recompute()
    return {"name": fillet.Name, "edges": edges, "radius": float(radius)}


def add_chamfer(edges: List[str], size: float) -> Dict[str, Any]:
    doc = _doc()
    if not edges:
        raise ValueError("edges must not be empty")
    first_obj_name = edges[0].split(".")[0]
    base = doc.getObject(first_obj_name)
    body = _body_of(base) if base.TypeId != "PartDesign::Body" else base
    with transaction("chamfer"):
        ch = doc.addObject("PartDesign::Chamfer", "Chamfer")
        body.addObject(ch)
        ch.Base = (base, [e.split(".", 1)[1] for e in edges])
        ch.Size = float(size)
        doc.recompute()
    return {"name": ch.Name, "edges": edges, "size": float(size)}


def add_revolution(sketch: str, axis: str = "Y", angle: float = 360.0) -> Dict[str, Any]:
    doc, sk, body = _resolve_sketch(sketch)
    with transaction(f"revolve {sketch}"):
        rev = doc.addObject("PartDesign::Revolution", "Revolution")
        body.addObject(rev)
        rev.Profile = sk
        rev.ReferenceAxis = (body.Origin.getObject(f"{axis.upper()}_Axis"), [""]) if body.Origin else None
        rev.Angle = float(angle)
        sk.Visibility = False
        doc.recompute()
    return {"name": rev.Name, "sketch": sk.Name, "angle": float(angle)}


TOOLS = [
    (
        {
            "name": "add_pad",
            "description": "Pad (extrude) a sketch into a solid inside its body.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sketch": {"type": "string"},
                    "length": {"type": "number", "description": "mm"},
                    "direction": {"type": "string", "enum": ["normal", "symmetric", "two_length"]},
                    "length2": {"type": "number", "description": "mm, only for direction=two_length"},
                    "reversed_": {"type": "boolean"},
                },
                "required": ["sketch", "length"],
                "additionalProperties": False,
            },
        },
        add_pad,
    ),
    (
        {
            "name": "add_pocket",
            "description": "Pocket (subtract) a sketch from its body.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sketch": {"type": "string"},
                    "depth": {"type": "number"},
                    "through_all": {"type": "boolean"},
                },
                "required": ["sketch", "depth"],
                "additionalProperties": False,
            },
        },
        add_pocket,
    ),
    (
        {
            "name": "add_hole",
            "description": "Drill a PartDesign Hole from a sketch containing its center circles. Optional counterbore.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sketch": {"type": "string"},
                    "diameter": {"type": "number"},
                    "depth": {"type": "number"},
                    "through_all": {"type": "boolean"},
                    "counterbore_diameter": {"type": "number"},
                    "counterbore_depth": {"type": "number"},
                },
                "required": ["sketch", "diameter"],
                "additionalProperties": False,
            },
        },
        add_hole,
    ),
    (
        {
            "name": "add_fillet",
            "description": "Round edges with a PartDesign Fillet. Edges are 'ObjectName.EdgeN' references, e.g. 'Pad.Edge3'.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "edges": {"type": "array", "items": {"type": "string"}},
                    "radius": {"type": "number"},
                },
                "required": ["edges", "radius"],
                "additionalProperties": False,
            },
        },
        add_fillet,
    ),
    (
        {
            "name": "add_chamfer",
            "description": "Chamfer edges with a PartDesign Chamfer.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "edges": {"type": "array", "items": {"type": "string"}},
                    "size": {"type": "number"},
                },
                "required": ["edges", "size"],
                "additionalProperties": False,
            },
        },
        add_chamfer,
    ),
    (
        {
            "name": "add_revolution",
            "description": "Revolve a sketch around a body axis (X/Y/Z) to create a solid.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sketch": {"type": "string"},
                    "axis": {"type": "string", "enum": ["X", "Y", "Z"]},
                    "angle": {"type": "number"},
                },
                "required": ["sketch"],
                "additionalProperties": False,
            },
        },
        add_revolution,
    ),
]
