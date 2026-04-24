# FreeCAD Agentic

Embed Claude inside FreeCAD as a dockable chat panel. Talk to Claude while looking at the 3D view and have it create, inspect, and parametrically edit the active document. Every tool call is wrapped in a single undo-able transaction, so **one Ctrl+Z reverts one Claude action**.

- **Workbench:** `Agentic` (appears in the standard workbench dropdown)
- **UI:** dockable chat panel on the right
- **Engine:** Anthropic Python SDK running inside FreeCAD's embedded interpreter
- **License:** LGPL-2.1-or-later

## Install (development)

Requires FreeCAD **1.0+** and the `anthropic` Python package installed into the same Python FreeCAD ships with.

```bash
# 1. Clone anywhere
git clone https://github.com/YourManz/free-cad-agentic.git ~/Work/free-cad-agentic

# 2. Symlink into FreeCAD's Mod dir
mkdir -p ~/.local/share/FreeCAD/Mod
ln -s ~/Work/free-cad-agentic ~/.local/share/FreeCAD/Mod/free-cad-agentic

# 3. Install the Anthropic SDK into FreeCAD's Python
#    (Linux system FreeCAD usually uses the system Python; adjust if you built from source)
pip install --user anthropic

# 4. Launch FreeCAD, switch to the "Agentic" workbench.
```

## Configure

Set your API key in one of two places:

- `Agentic → Agentic preferences` inside FreeCAD, or
- the `ANTHROPIC_API_KEY` environment variable.

Default model is `claude-opus-4-7`; override in preferences. `claude-sonnet-4-6` or `claude-haiku-4-5` are fine for lighter edits.

## What Claude can do

**Inspection**
- `list_objects`, `describe_object`

**Document lifecycle**
- `new_document`, `open_document`, `save`, `save_as`, `recompute`, `add_body`, `delete`

**Sketcher**
- `add_sketch` (attaches to XY/XZ/YZ datum planes by default)
- `add_sketch_geometry` (lines, circles, arcs, points)
- `add_sketch_constraint` (coincident, parallel, distance, radius, …)

**Part Design features**
- `add_pad`, `add_pocket`, `add_hole`, `add_fillet`, `add_chamfer`, `add_revolution`

**Parametric edits**
- `set_property` (e.g. `Pad.Length = 25`)
- `set_expression` (`Pad.Length = Sketch.Constraints.height + 2`)
- `rename`

**View / export**
- `fit_view`, `set_view`, `screenshot` (sent back to Claude as an image)
- `export` (STEP / STL / IGES)

## How it works

1. You type a message in the dock panel.
2. A worker thread calls `anthropic.messages.create()` with the full tool schema + a system prompt that teaches Claude about FreeCAD conventions (datum planes, full constraints, units).
3. Claude replies with `tool_use` blocks; each tool runs inside `App.openTransaction(...)` so one undo reverts one Claude action.
4. After mutating tools, Claude can call `screenshot`; the PNG is embedded back as an image block so Claude literally sees the viewport.
5. The loop continues until Claude emits a text-only reply, which appears in the transcript.

Prompt caching is applied to the tool schema + system prompt so turns after the first are cheap.

## Testing

From the repo root:

```bash
freecadcmd -c "exec(open('tests/run.py').read())"
```

The smoke test builds a plate, adds constraints, pads it, tweaks the pad length, and exports STEP — asserting the model recomputes cleanly at every step.

## Submitting to the FreeCAD Addon Manager

Once the repo is tagged `0.1.0` on GitHub, submit a PR to [FreeCAD/FreeCAD-addons](https://github.com/FreeCAD/FreeCAD-addons) adding this repository URL. After that it appears in every FreeCAD user's built-in Addon Manager.

## Safety

- The API key is stored in FreeCAD's parameter store (plaintext, same place other addons store tokens). Use the env var on shared machines.
- Claude has write access to the active document. There is no confirmation step before individual tool calls — **undo is your seatbelt**. Start with disposable files.
- No network calls happen other than to `api.anthropic.com`. All CAD operations are local.
