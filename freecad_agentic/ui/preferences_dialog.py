"""Simple preferences dialog."""
from __future__ import annotations

import FreeCADGui

from .. import preferences
from ..qt import QtWidgets


class PreferencesDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agentic Preferences")
        self.setMinimumWidth(520)

        form = QtWidgets.QFormLayout(self)

        self.api_key = QtWidgets.QLineEdit(preferences.get_api_key())
        self.api_key.setEchoMode(QtWidgets.QLineEdit.Password)
        self.api_key.setPlaceholderText("sk-ant-...")
        form.addRow("Anthropic API key", self.api_key)

        self.model = QtWidgets.QComboBox()
        self.model.setEditable(True)
        self.model.addItems([
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
        ])
        self.model.setCurrentText(preferences.get_model())
        form.addRow("Model", self.model)

        self.max_tokens = QtWidgets.QSpinBox()
        self.max_tokens.setRange(1024, 64000)
        self.max_tokens.setValue(preferences.get_max_tokens())
        form.addRow("Max output tokens", self.max_tokens)

        self.system_extra = QtWidgets.QPlainTextEdit(preferences.get_system_prompt_extra())
        self.system_extra.setPlaceholderText("Additional system prompt (optional)")
        self.system_extra.setFixedHeight(100)
        form.addRow("System prompt extra", self.system_extra)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _save(self):
        preferences.set_api_key(self.api_key.text().strip())
        preferences.set_model(self.model.currentText().strip())
        preferences.set_max_tokens(self.max_tokens.value())
        preferences.set_system_prompt_extra(self.system_extra.toPlainText())
        self.accept()


def show_preferences_dialog():
    dlg = PreferencesDialog(FreeCADGui.getMainWindow())
    dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
