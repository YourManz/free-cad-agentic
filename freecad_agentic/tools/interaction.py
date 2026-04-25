"""Tools that ask the human for input. These run on the main thread (the
dispatcher marshals them) so it's safe to pop a Qt dialog directly.
"""
from __future__ import annotations

from typing import Any, Dict


def ask_user(question: str, default: str = "") -> Dict[str, Any]:
    import FreeCADGui

    from ..qt import QtWidgets

    parent = FreeCADGui.getMainWindow()
    text, ok = QtWidgets.QInputDialog.getText(
        parent,
        "Agentic — input requested",
        question,
        QtWidgets.QLineEdit.Normal,
        default,
    )
    if not ok:
        return {"answered": False, "reason": "user cancelled the dialog"}
    return {"answered": True, "response": text}


TOOLS = [
    (
        {
            "name": "ask_user",
            "description": "Pop a small dialog asking the user a question and return their typed answer. Use this when the request leaves a meaningful choice unspecified (units, hole size, screw standard, orientation, material). Do not use for trivial confirmations.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question shown to the user."},
                    "default": {"type": "string", "description": "Optional pre-filled answer."},
                },
                "required": ["question"],
                "additionalProperties": False,
            },
        },
        ask_user,
    ),
]
