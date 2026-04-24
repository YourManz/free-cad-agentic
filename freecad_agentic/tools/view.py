"""Viewport / screenshot / export tools."""
from __future__ import annotations

import base64
import os
import tempfile
from typing import Any, Dict

import FreeCAD

try:
    import FreeCADGui
except ImportError:  # pragma: no cover - headless
    FreeCADGui = None  # type: ignore


def _active_view():
    if FreeCADGui is None or FreeCADGui.ActiveDocument is None:
        return None
    return FreeCADGui.ActiveDocument.ActiveView


def fit_view() -> Dict[str, Any]:
    view = _active_view()
    if view is None:
        return {"ok": False, "reason": "no active GUI view"}
    view.fitAll()
    return {"ok": True}


def set_view(direction: str = "isometric") -> Dict[str, Any]:
    view = _active_view()
    if view is None:
        return {"ok": False, "reason": "no active GUI view"}
    mapping = {
        "isometric": "viewIsometric",
        "top": "viewTop",
        "bottom": "viewBottom",
        "front": "viewFront",
        "rear": "viewRear",
        "left": "viewLeft",
        "right": "viewRight",
    }
    method_name = mapping.get(direction.lower())
    if method_name is None:
        raise ValueError(f"direction must be one of {list(mapping)}")
    getattr(view, method_name)()
    view.fitAll()
    return {"ok": True, "direction": direction}


def screenshot(width: int = 800, height: int = 600) -> Dict[str, Any]:
    view = _active_view()
    if view is None:
        return {"ok": False, "reason": "no active GUI view"}
    path = os.path.join(tempfile.gettempdir(), f"freecad_agentic_{os.getpid()}.png")
    view.saveImage(path, int(width), int(height), "Current")
    with open(path, "rb") as fh:
        data = fh.read()
    os.unlink(path)
    return {
        "ok": True,
        "media_type": "image/png",
        "data_base64": base64.b64encode(data).decode("ascii"),
        "width": int(width),
        "height": int(height),
    }


def export(path: str, format: str = "step") -> Dict[str, Any]:
    doc = FreeCAD.ActiveDocument
    if doc is None:
        raise RuntimeError("no active document")
    path = os.path.expanduser(path)
    fmt = format.lower()
    shapes = [o for o in doc.Objects if hasattr(o, "Shape")]
    if not shapes:
        raise RuntimeError("document has no shapes to export")
    if fmt == "step":
        import Import

        Import.export(shapes, path)
    elif fmt == "stl":
        import Mesh

        Mesh.export(shapes, path)
    elif fmt == "iges":
        import Import

        Import.export(shapes, path)
    else:
        raise ValueError(f"unsupported format: {format!r}")
    return {"path": path, "format": fmt, "shapes": [s.Name for s in shapes]}


TOOLS = [
    (
        {
            "name": "fit_view",
            "description": "Zoom the active 3D view to fit all visible geometry.",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        fit_view,
    ),
    (
        {
            "name": "set_view",
            "description": "Orient the camera to a standard view direction and fit all.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["isometric", "top", "bottom", "front", "rear", "left", "right"],
                    }
                },
                "required": ["direction"],
                "additionalProperties": False,
            },
        },
        set_view,
    ),
    (
        {
            "name": "screenshot",
            "description": "Capture the current 3D view as a PNG. Returns base64-encoded image data that the caller includes as an image block in the next message.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "width": {"type": "integer", "minimum": 128, "maximum": 4096},
                    "height": {"type": "integer", "minimum": 128, "maximum": 4096},
                },
                "additionalProperties": False,
            },
        },
        screenshot,
    ),
    (
        {
            "name": "export",
            "description": "Export all shape-bearing objects to STEP, STL, or IGES.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "format": {"type": "string", "enum": ["step", "stl", "iges"]},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
        export,
    ),
]
