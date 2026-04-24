"""Document-level tools: open / new / save / inspect."""
from __future__ import annotations

import os
from typing import Any, Dict, List

import FreeCAD

from ..transaction import transaction


def _active_or_raise():
    doc = FreeCAD.ActiveDocument
    if doc is None:
        raise RuntimeError("no active document; call new_document or open_document first")
    return doc


def _summarize(obj) -> Dict[str, Any]:
    return {
        "name": obj.Name,
        "label": obj.Label,
        "type": obj.TypeId,
        "in_list": [p.Name for p in getattr(obj, "InList", [])],
        "visible": getattr(obj, "Visibility", True),
        "errored": bool(getattr(obj, "State", None) and "Invalid" in obj.State),
    }


def list_objects() -> Dict[str, Any]:
    doc = _active_or_raise()
    return {
        "document": doc.Name,
        "label": doc.Label,
        "file": doc.FileName or None,
        "objects": [_summarize(o) for o in doc.Objects],
    }


def describe_object(name: str) -> Dict[str, Any]:
    doc = _active_or_raise()
    obj = doc.getObject(name)
    if obj is None:
        raise KeyError(f"no object named {name!r}")
    props: Dict[str, Any] = {}
    for prop in obj.PropertiesList:
        try:
            value = getattr(obj, prop)
        except Exception as exc:  # pragma: no cover - defensive
            value = f"<unreadable: {exc}>"
        props[prop] = _safe(value)
    exprs: List[Dict[str, str]] = []
    for path, expr in getattr(obj, "ExpressionEngine", []) or []:
        exprs.append({"path": path, "expression": expr})
    return {
        "summary": _summarize(obj),
        "properties": props,
        "expressions": exprs,
    }


def _safe(value: Any) -> Any:
    if hasattr(value, "UserString"):
        return value.UserString
    if hasattr(value, "Name") and hasattr(value, "TypeId"):
        return {"ref": value.Name}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def new_document(name: str = "Unnamed") -> Dict[str, Any]:
    doc = FreeCAD.newDocument(name)
    return {"name": doc.Name}


def open_document(path: str) -> Dict[str, Any]:
    path = os.path.expanduser(path)
    doc = FreeCAD.openDocument(path)
    return {"name": doc.Name, "file": doc.FileName}


def save() -> Dict[str, Any]:
    doc = _active_or_raise()
    if not doc.FileName:
        raise RuntimeError("document has no path; use save_as(path)")
    doc.save()
    return {"file": doc.FileName}


def save_as(path: str) -> Dict[str, Any]:
    doc = _active_or_raise()
    path = os.path.expanduser(path)
    doc.saveAs(path)
    return {"file": doc.FileName}


def recompute() -> Dict[str, Any]:
    doc = _active_or_raise()
    doc.recompute()
    errored = []
    for obj in doc.Objects:
        state = getattr(obj, "State", None)
        if state and any(flag in state for flag in ("Invalid", "Touched")):
            errored.append({"name": obj.Name, "state": list(state)})
    return {"errored": errored}


def add_body(name: str = "Body") -> Dict[str, Any]:
    doc = _active_or_raise()
    with transaction(f"add_body {name}"):
        body = doc.addObject("PartDesign::Body", name)
        doc.recompute()
    return {"name": body.Name}


def delete(name: str) -> Dict[str, Any]:
    doc = _active_or_raise()
    if doc.getObject(name) is None:
        raise KeyError(f"no object named {name!r}")
    with transaction(f"delete {name}"):
        doc.removeObject(name)
    return {"deleted": name}


TOOLS = [
    (
        {
            "name": "list_objects",
            "description": "List every object in the active FreeCAD document with its name, type, label, parent chain, and whether it is errored.",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        list_objects,
    ),
    (
        {
            "name": "describe_object",
            "description": "Return the full property dump of an object by name, including expressions bound to its properties.",
            "input_schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
        },
        describe_object,
    ),
    (
        {
            "name": "new_document",
            "description": "Create a new empty FreeCAD document and make it active.",
            "input_schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        new_document,
    ),
    (
        {
            "name": "open_document",
            "description": "Open a .FCStd file from disk and make it active.",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
        open_document,
    ),
    (
        {
            "name": "save",
            "description": "Save the active document to its existing path. Fails if the document has never been saved.",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        save,
    ),
    (
        {
            "name": "save_as",
            "description": "Save the active document to a new path. Use this for a brand new document.",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
        save_as,
    ),
    (
        {
            "name": "recompute",
            "description": "Force the active document to recompute. Returns any objects that are still in an invalid or touched state.",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        recompute,
    ),
    (
        {
            "name": "add_body",
            "description": "Add a new empty PartDesign Body to the active document. Bodies hold sketches and features.",
            "input_schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        add_body,
    ),
    (
        {
            "name": "delete",
            "description": "Delete an object from the active document by name.",
            "input_schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
        },
        delete,
    ),
]
