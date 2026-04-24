import os
import sys

import FreeCAD
import FreeCADGui

_ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
if _ADDON_DIR not in sys.path:
    sys.path.insert(0, _ADDON_DIR)


class AgenticWorkbench(FreeCADGui.Workbench):
    MenuText = "Agentic"
    ToolTip = "Chat with Claude to create and edit parametric models"
    Icon = os.path.join(_ADDON_DIR, "resources", "icon.svg")

    def Initialize(self):
        from freecad_agentic import commands  # noqa: F401

        self.appendToolbar("Agentic", ["Agentic_OpenChat", "Agentic_Preferences"])
        self.appendMenu("Agentic", ["Agentic_OpenChat", "Agentic_Preferences"])

    def Activated(self):
        from freecad_agentic.ui.chat_panel import show_chat_panel

        show_chat_panel()

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(AgenticWorkbench())
