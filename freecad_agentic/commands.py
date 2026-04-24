"""FreeCAD GUI commands registered on the workbench toolbar/menu."""
from __future__ import annotations

import os

import FreeCADGui

_ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ICON = os.path.join(_ADDON_DIR, "resources", "icon.svg")


class _OpenChat:
    def GetResources(self):
        return {
            "Pixmap": _ICON,
            "MenuText": "Open Claude chat",
            "ToolTip": "Toggle the Agentic chat panel",
        }

    def Activated(self):
        from .ui.chat_panel import show_chat_panel

        show_chat_panel()

    def IsActive(self):
        return True


class _Preferences:
    def GetResources(self):
        return {
            "Pixmap": _ICON,
            "MenuText": "Agentic preferences",
            "ToolTip": "Configure API key and model",
        }

    def Activated(self):
        from .ui.preferences_dialog import show_preferences_dialog

        show_preferences_dialog()

    def IsActive(self):
        return True


FreeCADGui.addCommand("Agentic_OpenChat", _OpenChat())
FreeCADGui.addCommand("Agentic_Preferences", _Preferences())
