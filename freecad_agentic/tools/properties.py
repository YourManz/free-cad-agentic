"""Property and expression edits — the bread and butter of parametric tweaks."""
from __future__ import annotations

from typing import Any, Dict

import FreeCAD

from ..transaction import transaction


def _get(name: str):
    doc = FreeCAD.ActiveDocument
    if doc is None:
        raise RuntimeError("no active document")
    obj = doc.getObject(name)
    if obj is None:
        raise KeyError(f"no object named {name!r}")
    return doc, obj


def set_property(name: str, prop: str, value: Any) -> Dict[str, Any]:
    doc, obj = _get(name)
    if prop not in obj.PropertiesList:
        raise KeyError(f"{name!r} has no property {prop!r}")
    with transaction(f"set {name}.{prop}"):
        current = getattr(obj, prop)
        # If current is a Quantity (length, angle, etc.), FreeCAD accepts numbers or strings.
        setattr(obj, prop, value)
        doc.recompute()
    return {"name": name, "prop": prop, "value": value, "previous": _safe(current)}


def set_expression(name: str, path: str, expression: str) -> Dict[str, Any]:
    doc, obj = _get(name)
    with transaction(f"expr {name}.{path}"):
        obj.setExpression(path, expression or None)
        doc.recompute()
    return {"name": name, "path": path, "expression": expression}


def rename(name: str, label: str) -> Dict[str, Any]:
    doc, obj = _get(name)
    with transaction(f"rename {name}"):
        obj.Label = label
    return {"name": name, "label": obj.Label}


def _safe(v: Any) -> Any:
    if hasattr(v, "UserString"):
        return v.UserString
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return repr(v)


TOOLS = [
    (
        {
            "name": "set_property",
            "description": "Set a property on an object by name. Works for any writable property including Length, Radius, Placement.Base.x, etc. For nested properties use set_expression instead.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Object name (not label)"},
                    "prop": {"type": "string"},
                    "value": {
                        "description": "Number, string, or boolean. For lengths, a plain number is interpreted in mm."
                    },
                },
                "required": ["name", "prop", "value"],
                "additionalProperties": False,
            },
        },
        set_property,
    ),
    (
        {
            "name": "set_expression",
            "description": "Bind a property to a FreeCAD expression, e.g. Pad.Length = Sketch.Constraints.height + 2. Pass an empty string to clear.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "path": {"type": "string", "description": "Property path, e.g. 'Length' or 'Placement.Base.x'"},
                    "expression": {"type": "string"},
                },
                "required": ["name", "path", "expression"],
                "additionalProperties": False,
            },
        },
        set_expression,
    ),
    (
        {
            "name": "rename",
            "description": "Change an object's user-facing Label. Does not change its internal Name.",
            "input_schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "label": {"type": "string"}},
                "required": ["name", "label"],
                "additionalProperties": False,
            },
        },
        rename,
    ),
]
