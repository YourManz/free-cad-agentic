"""Anthropic tool-use loop running inside the FreeCAD process.

Design notes:
- We run our own ~100-line loop rather than using the Agent SDK. Dependencies stay
  minimal (just `anthropic`) which matters for an in-process addon.
- Prompt caching is applied to the tool schema and system prompt so each turn is
  cheap after the first.
- Every tool result is JSON-stringified. If a tool returns a screenshot payload
  (media_type + data_base64), we also attach an image content block alongside the
  tool_result so Claude can literally see the viewport.
"""
from __future__ import annotations

import json
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

These are real differences from 0.x / 1.0 that have tripped agents up. Use this \
list before guessing:

- **Sketcher attachment:** `sketch.Support = (plane, [""])` is removed. Use \
`sketch.AttachmentSupport = (plane, [""])` (the tool already handles this).
- **Sketcher inspection:** `getHighestVertexIndex()` is gone. Use \
`sketch.GeometryCount`, `len(sketch.Constraints)`, and `sketch.solve()` (returns \
0 when fully constrained).
- **Sketcher constraints:** `Sketcher.Constraint(type, *flat_args)` — point refs \
must be flattened to `(geoId, pointPos)` pairs passed as separate integers, not \
nested lists. PointPos: 0=any, 1=start, 2=end, 3=center. The fixed origin vertex \
is geoId `-1`, pointPos `1`.
- **Hole feature:** `DepthType` is now a string `"Dimension"` or `"ThroughAll"`, \
not an int. `HoleCutType = "Counterbore"` / `"Countersink"` / `"None"`.
- **Pocket feature:** `Type` as int is still accepted: 0=Dimension, 1=ThroughAll, \
2=UpToFirst, 3=UpToFace, 4=TwoLengths.
- **Pad feature:** `Type = 4` for TwoLengths still works; `Midplane = True` for \
symmetric. `Reversed` flips direction.
- **PartDesign Body required:** Every Pad/Pocket/Hole/Fillet must live inside a \
`PartDesign::Body`. If the document has no body yet, call `add_body` first.
- **Origin axes:** Reference `body.Origin.getObject("X_Axis")` (or Y_Axis, \
Z_Axis) — these are the default ref axes for Revolution etc.
- **Recompute semantics:** the tools auto-recompute after mutations, but if you \
see "Touched" state in `recompute()` output, something upstream failed — fix the \
upstream object before retrying the current one.
- **Property introspection:** `obj.PropertiesList` gives names; \
`obj.getTypeIdOfProperty(name)` gives type; `obj.ExpressionEngine` is a list of \
`(path, expression)` pairs for any bound expressions.

## Unrelated but useful: Obsidian Bases

The user's notes vault uses Obsidian, and Obsidian's **Bases** (new in 1.7+) \
sometimes comes up. Bases are a no-code database view over notes, stored as \
`.base` files with YAML frontmatter. Key facts:

- A `.base` file is YAML at the top (filters, views, formulas) and is read by \
Obsidian's Bases core plugin. Do NOT confuse with Dataview — Bases is the newer \
first-party replacement.
- Top-level keys: `filters` (logical tree with `and`/`or`/`not` of conditions), \
`formulas` (named expressions reused in views), `properties` (display config per \
property, e.g. `property.note.customName.displayName`), and `views` (a list of \
view configs).
- Each view has `type: table | cards | ...`, `name`, `filters`, `order` (list \
of property refs), `sort` (list of `{property, direction}`), and optionally \
`limit`.
- Property references use dotted paths like `note.tags`, `file.name`, \
`file.mtime`, `note.status`. Custom frontmatter keys live under `note.*`.
- Formulas use a small expression language (`contains`, `!`, `&&`, `||`, \
`startsWith`, dates like `now()`, `date(note.creationDate)`).
- When editing `.base` files directly, validate YAML carefully — Obsidian \
silently shows an empty view on malformed YAML instead of an error.
- Prefer editing via the Obsidian UI when possible; only hand-edit when doing \
batch changes across many bases.
"""


@dataclass
class AgentResult:
    text: str
    turns: int
    tool_calls: int
    error: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)


def _make_client():
    from anthropic import Anthropic

    api_key = preferences.get_api_key()
    if not api_key:
        raise RuntimeError(
            "No Anthropic API key configured. Set it in Agentic preferences or the "
            "ANTHROPIC_API_KEY environment variable."
        )
    return Anthropic(api_key=api_key)


def _cached_tools() -> List[Dict[str, Any]]:
    schemas = tool_schemas()
    # Apply cache breakpoint to the last tool so the entire tool block is cached.
    if schemas:
        schemas = [dict(s) for s in schemas]
        schemas[-1] = dict(schemas[-1], cache_control={"type": "ephemeral"})
    return schemas


def _cached_system() -> List[Dict[str, Any]]:
    extra = preferences.get_system_prompt_extra().strip()
    text = SYSTEM_PROMPT + (("\n\n" + extra) if extra else "")
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def _result_blocks(tool_use_id: str, result: Any) -> List[Dict[str, Any]]:
    """Produce the tool_result content blocks for a tool invocation.

    If the tool result looks like a screenshot payload, we attach a separate image
    block in the same user message so Claude sees the image.
    """
    blocks: List[Dict[str, Any]] = [
        {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": json.dumps(_strip_image(result), default=str),
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


def run_turn(
    user_text: str,
    history: List[Dict[str, Any]],
    max_iterations: int = 12,
    status_cb: Optional[Callable[[str], None]] = None,
) -> AgentResult:
    """Run one user turn: append message, loop tool_use until stop. Mutates history in place."""
    client = _make_client()
    model = preferences.get_model()
    max_tokens = preferences.get_max_tokens()

    history.append({"role": "user", "content": [{"type": "text", "text": user_text}]})

    tool_calls = 0
    turns = 0
    try:
        for _ in range(max_iterations):
            turns += 1
            if status_cb:
                status_cb(f"calling {model}…")
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=_cached_system(),
                tools=_cached_tools(),
                messages=history,
            )
            assistant_content = [_block_to_dict(b) for b in response.content]
            history.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason != "tool_use":
                text = "\n".join(b["text"] for b in assistant_content if b.get("type") == "text")
                return AgentResult(text=text.strip(), turns=turns, tool_calls=tool_calls, history=history)

            # Run each tool_use block and assemble the tool_result user message.
            tool_message: List[Dict[str, Any]] = []
            for block in assistant_content:
                if block.get("type") != "tool_use":
                    continue
                tool_calls += 1
                name = block["name"]
                args = block.get("input") or {}
                if status_cb:
                    status_cb(f"running {name}…")
                try:
                    result = dispatch(name, args)
                except Exception as exc:
                    tb = traceback.format_exc(limit=3)
                    tool_message.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "is_error": True,
                            "content": f"{type(exc).__name__}: {exc}\n{tb}",
                        }
                    )
                    continue
                tool_message.extend(_result_blocks(block["id"], result))
            history.append({"role": "user", "content": tool_message})
        return AgentResult(
            text="(stopped after max iterations)",
            turns=turns,
            tool_calls=tool_calls,
            error="max_iterations",
            history=history,
        )
    except Exception as exc:
        tb = traceback.format_exc()
        return AgentResult(
            text="",
            turns=turns,
            tool_calls=tool_calls,
            error=f"{type(exc).__name__}: {exc}\n{tb}",
            history=history,
        )


def _block_to_dict(block: Any) -> Dict[str, Any]:
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)
    if hasattr(block, "to_dict"):
        return block.to_dict()
    return dict(block)
