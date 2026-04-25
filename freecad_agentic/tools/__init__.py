"""Tool registry. Each module exposes a TOOLS list of (schema, callable) pairs."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from . import document, features, interaction, properties, sketch, view

_MODULES = [document, sketch, features, properties, view, interaction]

# (schema_dict, callable)
Tool = Tuple[Dict[str, Any], Callable[..., Any]]


def all_tools() -> List[Tool]:
    tools: List[Tool] = []
    for mod in _MODULES:
        tools.extend(getattr(mod, "TOOLS", []))
    return tools


def tool_schemas() -> List[Dict[str, Any]]:
    return [schema for schema, _fn in all_tools()]


def dispatch(name: str, arguments: Dict[str, Any]) -> Any:
    for schema, fn in all_tools():
        if schema["name"] == name:
            return fn(**(arguments or {}))
    raise KeyError(f"unknown tool: {name}")
