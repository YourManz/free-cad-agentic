"""Dockable Claude chat panel inside FreeCAD.

The panel is a QDockWidget with a transcript (QTextBrowser) + input (QTextEdit) +
Send/Clear buttons. API calls run on a QThread so the FreeCAD GUI stays responsive.
"""
from __future__ import annotations

from typing import Any, Dict, List

import FreeCADGui

from ..agent.loop import run_turn
from ..qt import Qt, QtCore, QtGui, QtWidgets, Signal

_PANEL_INSTANCE = None
_PANEL_OBJECT_NAME = "AgenticChatPanel"


class _AgentWorker(QtCore.QObject):
    finished = Signal(object)  # AgentResult
    status = Signal(str)

    def __init__(self, user_text: str, history: List[Dict[str, Any]]):
        super().__init__()
        self._user_text = user_text
        self._history = history

    def run(self):
        result = run_turn(self._user_text, self._history, status_cb=lambda s: self.status.emit(s))
        self.finished.emit(result)


class ChatPanel(QtWidgets.QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Agentic", parent)
        self.setObjectName(_PANEL_OBJECT_NAME)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self._history: List[Dict[str, Any]] = []
        self._thread: QtCore.QThread | None = None
        self._worker: _AgentWorker | None = None

        root = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(root)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.transcript = QtWidgets.QTextBrowser(root)
        self.transcript.setOpenExternalLinks(True)
        layout.addWidget(self.transcript, 1)

        self.input = QtWidgets.QTextEdit(root)
        self.input.setPlaceholderText("Ask Claude to inspect, create, or modify the model…  (Ctrl+Enter to send)")
        self.input.setFixedHeight(90)
        layout.addWidget(self.input)

        row = QtWidgets.QHBoxLayout()
        self.status_label = QtWidgets.QLabel("ready", root)
        self.status_label.setStyleSheet("color: gray;")
        row.addWidget(self.status_label, 1)
        self.clear_btn = QtWidgets.QPushButton("Clear", root)
        self.clear_btn.clicked.connect(self._clear)
        row.addWidget(self.clear_btn)
        self.send_btn = QtWidgets.QPushButton("Send", root)
        self.send_btn.setDefault(True)
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.send_btn)
        layout.addLayout(row)

        self.setWidget(root)

        send_sc = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Return"), self.input)
        send_sc.activated.connect(self._send)

        self._append_system("Agentic ready. Set ANTHROPIC_API_KEY or configure via Agentic → Preferences.")

    def _append_system(self, text: str):
        self.transcript.append(f"<span style='color:gray'>· {_escape(text)}</span>")

    def _append_user(self, text: str):
        self.transcript.append(f"<p><b>You:</b> {_escape(text)}</p>")

    def _append_assistant(self, text: str):
        safe = _escape(text).replace("\n", "<br>")
        self.transcript.append(f"<p><b>Claude:</b> {safe}</p>")

    def _append_error(self, text: str):
        self.transcript.append(f"<pre style='color:#c33'>{_escape(text)}</pre>")

    def _clear(self):
        self._history.clear()
        self.transcript.clear()
        self._append_system("conversation cleared")

    def _send(self):
        if self._thread is not None:
            return
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        self._append_user(text)
        self.send_btn.setEnabled(False)
        self.status_label.setText("thinking…")

        self._thread = QtCore.QThread(self)
        self._worker = _AgentWorker(text, self._history)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.status.connect(self._on_status)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    def _on_status(self, msg: str):
        self.status_label.setText(msg)

    def _on_finished(self, result):
        if result.error:
            self._append_error(result.error)
        if result.text:
            self._append_assistant(result.text)
        self.status_label.setText(
            f"ready · {result.turns} turn(s), {result.tool_calls} tool call(s)"
        )
        self.send_btn.setEnabled(True)
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread = None
            self._worker = None


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def show_chat_panel():
    global _PANEL_INSTANCE
    main_window = FreeCADGui.getMainWindow()
    if _PANEL_INSTANCE is None:
        _PANEL_INSTANCE = ChatPanel(main_window)
        main_window.addDockWidget(Qt.RightDockWidgetArea, _PANEL_INSTANCE)
    _PANEL_INSTANCE.show()
    _PANEL_INSTANCE.raise_()
    return _PANEL_INSTANCE
