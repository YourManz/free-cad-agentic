import os
import sys
import traceback

_LOG = os.path.expanduser("~/.local/share/FreeCAD/v1-1/agentic_init.log")


def _log(msg):
    try:
        with open(_LOG, "a") as fh:
            fh.write(msg + "\n")
    except Exception:
        pass


try:
    try:
        _ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        # FreeCAD exec's us without __file__ on some builds — find ourselves instead.
        _ADDON_DIR = None
        for base in [
            os.path.expanduser("~/.local/share/FreeCAD/v1-1/Mod/free-cad-agentic"),
            os.path.expanduser("~/.FreeCAD/Mod/free-cad-agentic"),
            os.path.expanduser("~/.local/share/FreeCAD/Mod/free-cad-agentic"),
        ]:
            if os.path.isdir(base):
                _ADDON_DIR = base
                break
        if _ADDON_DIR is None:
            raise RuntimeError("could not locate free-cad-agentic addon directory")

    if _ADDON_DIR not in sys.path:
        sys.path.insert(0, _ADDON_DIR)

    _log(f"InitGui: loading from {_ADDON_DIR}")

    import FreeCAD  # noqa: F401
    import FreeCADGui

    class AgenticWorkbench(FreeCADGui.Workbench):
        MenuText = "Agentic"
        ToolTip = "Chat with Claude to create and edit parametric models"
        Icon = os.path.join(_ADDON_DIR, "resources", "icon.svg")

        def Initialize(self):
            try:
                from freecad_agentic import commands  # noqa: F401

                self.appendToolbar("Agentic", ["Agentic_OpenChat", "Agentic_Preferences"])
                self.appendMenu("Agentic", ["Agentic_OpenChat", "Agentic_Preferences"])
                _log("Workbench.Initialize: commands registered")
            except Exception:
                _log("Workbench.Initialize FAILED:\n" + traceback.format_exc())
                raise

        def Activated(self):
            try:
                from freecad_agentic.ui.chat_panel import show_chat_panel

                show_chat_panel()
            except Exception:
                _log("Workbench.Activated FAILED:\n" + traceback.format_exc())
                raise

        def Deactivated(self):
            pass

        def GetClassName(self):
            return "Gui::PythonWorkbench"

    FreeCADGui.addWorkbench(AgenticWorkbench())
    _log("InitGui: addWorkbench OK")
except Exception:
    _log("InitGui FAILED:\n" + traceback.format_exc())
    raise
