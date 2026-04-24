"""FreeCAD 1.1 namespace-package entry point.

FreeCAD auto-imports every `freecad.*.init_gui` module at startup. This file
registers the Agentic workbench. The heavy lifting lives in the top-level
`freecad_agentic` package, which is importable because each addon directory is
placed on sys.path by FreeCAD's Mod loader.
"""

from __future__ import annotations

import os
import sys
import traceback

import FreeCAD as App
import FreeCADGui as Gui

_LOG = os.path.expanduser("~/.local/share/FreeCAD/v1-1/agentic_init.log")


def _log(msg: str) -> None:
    try:
        with open(_LOG, "a") as fh:
            fh.write(msg + "\n")
    except Exception:
        pass
    try:
        App.Console.PrintMessage(f"[Agentic] {msg}\n")
    except Exception:
        pass


_ADDON_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ADDON_DIR not in sys.path:
    sys.path.insert(0, _ADDON_DIR)

_log(f"init_gui loading from {_ADDON_DIR}")


class AgenticWorkbench(Gui.Workbench):
    MenuText = "Agentic"
    ToolTip = "Chat with Claude to create and edit parametric models"
    Icon = os.path.join(_ADDON_DIR, "resources", "icon.svg")

    def GetClassName(self) -> str:  # noqa: N802
        return "Gui::PythonWorkbench"

    def Initialize(self) -> None:  # noqa: N802
        try:
            from freecad_agentic import commands  # noqa: F401

            self.appendToolbar("Agentic", ["Agentic_OpenChat", "Agentic_Preferences"])
            self.appendMenu("Agentic", ["Agentic_OpenChat", "Agentic_Preferences"])
            _log("Initialize: commands registered")
        except Exception:
            _log("Initialize FAILED:\n" + traceback.format_exc())
            raise

    def Activated(self) -> None:  # noqa: N802
        try:
            from freecad_agentic.ui.chat_panel import show_chat_panel

            show_chat_panel()
        except Exception:
            _log("Activated FAILED:\n" + traceback.format_exc())
            raise

    def Deactivated(self) -> None:  # noqa: N802
        pass


try:
    Gui.addWorkbench(AgenticWorkbench())
    _log("addWorkbench OK")
except Exception:
    _log("addWorkbench FAILED:\n" + traceback.format_exc())
    raise
