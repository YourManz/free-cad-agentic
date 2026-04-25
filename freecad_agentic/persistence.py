"""Persist chat history into a FreeCAD document.

We use `doc.Meta` (a string→string map serialized inside the `.FCStd` zip).
Image blocks are stripped before serializing — they're large and Claude can
re-screenshot on demand. Everything else (text, tool_use, tool_result) is kept
so the model has full context after a reload.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import FreeCAD

META_KEY = "AgenticHistory"


def _strip_for_storage(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for msg in history:
        content = msg.get("content")
        if isinstance(content, list):
            kept = []
            for block in content:
                if not isinstance(block, dict):
                    kept.append(block)
                    continue
                if block.get("type") == "image":
                    # Drop the base64 payload but leave a marker so the role/turn
                    # structure stays intact for any future viewer.
                    kept.append({"type": "text", "text": "[image omitted]"})
                    continue
                kept.append(block)
            out.append({"role": msg["role"], "content": kept})
        else:
            out.append(msg)
    return out


def save_history(doc: Optional["FreeCAD.Document"], history: List[Dict[str, Any]]) -> bool:
    if doc is None:
        return False
    try:
        payload = json.dumps(_strip_for_storage(history), separators=(",", ":"))
    except Exception:
        return False
    try:
        meta = dict(doc.Meta) if doc.Meta else {}
    except Exception:
        meta = {}
    if meta.get(META_KEY) == payload:
        return False  # no change, leave the doc clean
    meta[META_KEY] = payload
    try:
        doc.Meta = meta
        return True
    except Exception:
        return False


def load_history(doc: Optional["FreeCAD.Document"]) -> Optional[List[Dict[str, Any]]]:
    if doc is None:
        return None
    try:
        meta = dict(doc.Meta) if doc.Meta else {}
    except Exception:
        return None
    raw = meta.get(META_KEY)
    if not raw:
        return None
    try:
        loaded = json.loads(raw)
        if isinstance(loaded, list):
            return loaded
    except Exception:
        return None
    return None


def clear_history(doc: Optional["FreeCAD.Document"]) -> None:
    if doc is None:
        return
    try:
        meta = dict(doc.Meta) if doc.Meta else {}
    except Exception:
        return
    if META_KEY in meta:
        del meta[META_KEY]
        try:
            doc.Meta = meta
        except Exception:
            pass
