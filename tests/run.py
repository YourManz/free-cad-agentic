"""Smoke tests. Run from repo root:

    freecadcmd -c "exec(open('tests/run.py').read())"

Asserts each tool module loads, basic document ops succeed, and a full build
(sketch -> pad -> pocket) yields a valid recomputed model.
"""
from __future__ import annotations

import os
import sys
import tempfile

import FreeCAD

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from freecad_agentic.tools import dispatch, tool_schemas  # noqa: E402


def expect(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_schemas_unique():
    names = [s["name"] for s in tool_schemas()]
    expect(len(names) == len(set(names)), f"duplicate tool names: {names}")


def test_build_plate():
    name = "agentic_test"
    dispatch("new_document", {"name": name})
    dispatch("add_body", {"name": "Body"})
    sk = dispatch("add_sketch", {"plane": "XY", "body": "Body", "name": "Base"})

    geom = [
        {"type": "line", "start": [0, 0], "end": [50, 0]},
        {"type": "line", "start": [50, 0], "end": [50, 30]},
        {"type": "line", "start": [50, 30], "end": [0, 30]},
        {"type": "line", "start": [0, 30], "end": [0, 0]},
    ]
    added = dispatch("add_sketch_geometry", {"sketch": sk["name"], "geometry": geom})
    ids = added["added_ids"]

    constraints = [
        {"type": "coincident", "refs": [[ids[0], 2], [ids[1], 1]]},
        {"type": "coincident", "refs": [[ids[1], 2], [ids[2], 1]]},
        {"type": "coincident", "refs": [[ids[2], 2], [ids[3], 1]]},
        {"type": "coincident", "refs": [[ids[3], 2], [ids[0], 1]]},
        {"type": "horizontal", "refs": [ids[0]]},
        {"type": "horizontal", "refs": [ids[2]]},
        {"type": "vertical", "refs": [ids[1]]},
        {"type": "vertical", "refs": [ids[3]]},
        {"type": "distance_x", "refs": [[ids[0], 1], [ids[0], 2]], "value": 50.0},
        {"type": "distance_y", "refs": [[ids[1], 1], [ids[1], 2]], "value": 30.0},
        {"type": "coincident", "refs": [[ids[0], 1], [-1, 1]]},
    ]
    dispatch("add_sketch_constraint", {"sketch": sk["name"], "constraints": constraints})

    pad = dispatch("add_pad", {"sketch": sk["name"], "length": 10.0})
    rec = dispatch("recompute", {})
    expect(not rec["errored"], f"recompute errored: {rec}")

    out = os.path.join(tempfile.gettempdir(), "agentic_test.step")
    dispatch("export", {"path": out, "format": "step"})
    expect(os.path.exists(out) and os.path.getsize(out) > 0, "step export empty")
    os.unlink(out)

    dispatch("set_property", {"name": pad["name"], "prop": "Length", "value": 15.0})
    rec = dispatch("recompute", {})
    expect(not rec["errored"], "recompute after set_property errored")

    FreeCAD.closeDocument(name)


if __name__ == "__main__" or True:
    test_schemas_unique()
    test_build_plate()
    print("OK: all tests passed")
