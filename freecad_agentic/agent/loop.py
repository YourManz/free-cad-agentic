"""Anthropic tool-use loop running inside the FreeCAD process.

Streaming + cancellable. The UI worker supplies callbacks; this module:
- opens a streamed Messages request,
- pushes text deltas out as they arrive so the UI feels live,
- dispatches tool_use blocks after each streamed turn,
- checks the cancel flag between events and between tool calls,
- loops until the model stops with a non-tool_use stop_reason or cancel fires.

Prompt caching is applied to the tool schema and system prompt so every turn after
the first is cheap. We keep our own small loop instead of the Agent SDK because
we need to run in-process in FreeCAD with a minimal dep footprint.
"""
from __future__ import annotations

import json
import threading
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .. import preferences
from ..tools import dispatch, tool_schemas

SYSTEM_PROMPT = """You are an assistant embedded inside FreeCAD 1.1 (a parametric CAD \
application). The user can see the 3D viewport and you can see it too via the \
`screenshot` tool. You manipulate the active document using the provided tools.

Guiding principles:
- Prefer datum planes (XY/XZ/YZ) over model faces for new sketches — this avoids \
topological-naming breakage.
- Fully constrain sketches. After creating geometry, add constraints until the \
solver reports DOF = 0.
- After any mutating action, the document is recomputed automatically. If a tool \
result reports errored objects or non-zero DOF, diagnose and fix before moving on.
- Take a screenshot after non-trivial changes so you can verify visually. Cheap \
tweaks (one `set_property`) usually don't need a screenshot.
- Be concise. The user sees your text replies in a dock panel next to the viewport.
- When you hit an AttributeError or unexpected API shape, call `describe_object` \
on the object before guessing — your training data may predate FreeCAD 1.1.

Units are millimetres and degrees unless stated otherwise.

## FreeCAD 1.1 API gotchas (post-training-cutoff changes)

- **Sketcher attachment:** `sketch.Support = (plane, [""])` is removed. Use \
`sketch.AttachmentSupport = (plane, [""])` (the tool already handles this).
- **Sketcher inspection:** `getHighestVertexIndex()` is gone. Use \
`sketch.GeometryCount`, `len(sketch.Constraints)`, and `sketch.solve()` (returns \
0 when fully constrained).
- **Sketcher constraints:** point refs must be flattened to `(geoId, pointPos)` \
integer pairs, not nested lists. PointPos: 0=any, 1=start, 2=end, 3=center. The \
fixed origin vertex is geoId `-1`, pointPos `1`.
- **Hole feature:** `DepthType` is a string `"Dimension"` or `"ThroughAll"`. \
`HoleCutType` is `"Counterbore"` / `"Countersink"` / `"None"`.
- **PartDesign Body required:** every Pad/Pocket/Hole/Fillet lives inside a \
`PartDesign::Body`. If none exists, call `add_body` first.
- **Origin axes:** reference `body.Origin.getObject("X_Axis")` etc. for \
Revolution axes.
- **Recompute semantics:** tools auto-recompute. A "Touched" object in the \
recompute output means something upstream failed — fix upstream first.
- **Property introspection:** `obj.PropertiesList`, \
`obj.getTypeIdOfProperty(name)`, `obj.ExpressionEngine` for bound expressions.

## Unrelated but useful: Obsidian Bases

The user's notes vault uses Obsidian Bases (`.base` YAML files). Key facts:
- Top-level keys: `filters` (and/or/not tree), `formulas`, `properties`, `views`.
- Each view has `type: table|cards`, `name`, `filters`, `order`, `sort`, `limit`.
- Property refs are dotted: `note.tags`, `file.name`, `file.mtime`, `note.status`.
- Formulas use `contains`, `!`, `&&`, `||`, `startsWith`, `now()`, `date(...)`.
- Malformed YAML silently renders an empty view — validate carefully.
- Prefer the Obsidian UI; hand-edit only for batch changes.
"""


class AgentCancelled(Exception):
    pass


@dataclass
class StreamCallbacks:
    on_text_delta: Callable[[str], None] = lambda _s: None
    on_assistant_done: Callable[[], None] = lambda: None
    on_tool_start: Callable[[str, Dict[str, Any]], None] = lambda _n, _a: None
    on_tool_result: Callable[[str, Any, bool], None] = lambda _n, _r, _e: None
    on_status: Callable[[str], None] = lambda _s: None


@dataclass
class AgentResult:
    turns: int = 0
    tool_calls: int = 0
    error: Optional[str] = None
    cancelled: bool = False
    history: List[Dict[str, Any]] = field(default_factory=list)


def _make_client():
    from anthropic import Anthropic

    api_key = preferences.get_api_key()
    if not api_key:
        raise RuntimeError(
            "No Anthropic API key configured. Set it in Agentic preferences or the "
            "ANTHROPIC_API_KEY environment variable."
        )
    return Anthropic(api_key=api_key, max_retries=1)


def _cached_tools() -> List[Dict[str, Any]]:
    schemas = [dict(s) for s in tool_schemas()]
    if schemas:
        schemas[-1] = dict(schemas[-1], cache_control={"type": "ephemeral"})
    return schemas


def _cached_system() -> List[Dict[str, Any]]:
    extra = preferences.get_system_prompt_extra().strip()
    text = SYSTEM_PROMPT + (("\n\n" + extra) if extra else "")
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def _result_blocks(tool_use_id: str, result: Any, is_error: bool = False) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = [
        {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": json.dumps(_strip_image(result), default=str) if not is_error else str(result),
            **({"is_error": True} if is_error else {}),
        }
    ]
    if isinstance(result, dict) and result.get("media_type") and result.get("data_base64"):
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": result["media_type"],
                    "data": result["data_base64"],
                },
            }
        )
    return blocks


def _strip_image(value: Any) -> Any:
    if isinstance(value, dict) and "data_base64" in value:
        clone = dict(value)
        clone["data_base64"] = f"<{len(clone['data_base64'])} bytes omitted>"
        return clone
    return value


def _block_to_dict(block: Any) -> Dict[str, Any]:
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)
    if hasattr(block, "to_dict"):
        return block.to_dict()
    return dict(block)


def run_turn_stream(
    user_text: str,
    history: List[Dict[str, Any]],
    callbacks: StreamCallbacks,
    cancel_event: Optional[threading.Event] = None,
    max_iterations: int = 12,
) -> AgentResult:
    """Run one user turn with streaming. history is mutated in place."""
    if cancel_event is None:
        cancel_event = threading.Event()
    result = AgentResult(history=history)

    def check_cancel():
        if cancel_event.is_set():
            raise AgentCancelled()

    try:
        client = _make_client()
        model = preferences.get_model()
        max_tokens = preferences.get_max_tokens()

        history.append({"role": "user", "content": [{"type": "text", "text": user_text}]})

        for _ in range(max_iterations):
            check_cancel()
            result.turns += 1
            callbacks.on_status(f"streaming from {model}…")

            with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=_cached_system(),
                tools=_cached_tools(),
                messages=history,
            ) as stream:
                for event in stream:
                    check_cancel()
                    etype = getattr(event, "type", None)
                    if etype == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if delta is not None and getattr(delta, "type", None) == "text_delta":
                            callbacks.on_text_delta(getattr(delta, "text", "") or "")
                final_message = stream.get_final_message()

            assistant_content = [_block_to_dict(b) for b in final_message.content]
            history.append({"role": "assistant", "content": assistant_content})
            callbacks.on_assistant_done()

            if final_message.stop_reason != "tool_use":
                return result

            tool_message: List[Dict[str, Any]] = []
            for block in assistant_content:
                if block.get("type") != "tool_use":
                    continue
                check_cancel()
                name = block["name"]
                args = block.get("input") or {}
                result.tool_calls += 1
                callbacks.on_tool_start(name, args)
                try:
                    tool_result = dispatch(name, args)
                except Exception as exc:
                    tb = traceback.format_exc(limit=3)
                    msg = f"{type(exc).__name__}: {exc}\n{tb}"
                    callbacks.on_tool_result(name, msg, True)
                    tool_message.extend(_result_blocks(block["id"], msg, is_error=True))
                    continue
                callbacks.on_tool_result(name, tool_result, False)
                tool_message.extend(_result_blocks(block["id"], tool_result))
            history.append({"role": "user", "content": tool_message})

        result.error = "max_iterations"
        return result
    except AgentCancelled:
        result.cancelled = True
        callbacks.on_status("cancelled")
        return result
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        return result
