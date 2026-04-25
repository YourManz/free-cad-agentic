"""Dockable Claude chat panel inside FreeCAD.

Streaming transcript + cancel support. Architecture:
- Worker QObject lives on a QThread, runs the streaming agent loop.
- The worker emits Qt signals for each event (text delta, tool start/result,
  status, finished). The main thread updates the UI.
- Cancel is a threading.Event the worker polls between events and tool calls.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List

import FreeCADGui

from ..agent.loop import AgentResult, StreamCallbacks, run_turn_stream
from ..qt import Qt, QtCore, QtGui, QtWidgets, Signal
from ..tools import dispatch as _dispatch_tool

_PANEL_INSTANCE = None
_PANEL_OBJECT_NAME = "AgenticChatPanel"


class _MainThreadDispatcher(QtCore.QObject):
    """Lives on the GUI main thread. Worker thread calls run_tool(), which emits
    a queued signal so the actual FreeCAD API call happens on the main thread,
    then blocks on a threading.Event until the result is set. FreeCAD's Python
    bindings touch Coin3D/Qt and freeze if called from a non-main thread.
    """

    _request = Signal(str, object, object)  # name, args, holder dict

    def __init__(self, parent=None):
        super().__init__(parent)
        # QueuedConnection ensures the slot runs on this object's thread (main),
        # even when the signal is emitted from the worker thread.
        self._request.connect(self._on_request, Qt.QueuedConnection)

    def run_tool(self, name: str, args: Dict[str, Any]) -> Any:
        holder: Dict[str, Any] = {"event": threading.Event(), "result": None, "error": None}
        self._request.emit(name, args, holder)
        holder["event"].wait()
        if holder["error"] is not None:
            raise holder["error"]
        return holder["result"]

    def _on_request(self, name: str, args: Dict[str, Any], holder: Dict[str, Any]):
        try:
            holder["result"] = _dispatch_tool(name, args)
        except Exception as exc:
            holder["error"] = exc
        finally:
            holder["event"].set()


class _AgentWorker(QtCore.QObject):
    text_delta = Signal(str)
    assistant_done = Signal()
    tool_start = Signal(str, object)
    tool_result = Signal(str, object, bool)
    status = Signal(str)
    finished = Signal(object)  # AgentResult

    def __init__(self, user_text: str, history: List[Dict[str, Any]], cancel_event: threading.Event, dispatcher: "_MainThreadDispatcher"):
        super().__init__()
        self._user_text = user_text
        self._history = history
        self._cancel_event = cancel_event
        self._dispatcher = dispatcher

    def run(self):
        cb = StreamCallbacks(
            on_text_delta=self.text_delta.emit,
            on_assistant_done=self.assistant_done.emit,
            on_tool_start=lambda n, a: self.tool_start.emit(n, a),
            on_tool_result=lambda n, r, e: self.tool_result.emit(n, r, e),
            on_status=self.status.emit,
        )
        result = run_turn_stream(
            self._user_text,
            self._history,
            cb,
            cancel_event=self._cancel_event,
            dispatch_tool=self._dispatcher.run_tool,
        )
        self.finished.emit(result)


class ChatPanel(QtWidgets.QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Agentic", parent)
        self.setObjectName(_PANEL_OBJECT_NAME)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(420)

        self._history: List[Dict[str, Any]] = []
        self._thread: QtCore.QThread | None = None
        self._worker: _AgentWorker | None = None
        self._cancel_event: threading.Event | None = None
        self._streaming_open = False  # whether an <p>Claude: paragraph is currently open
        self._dispatcher = _MainThreadDispatcher(self)  # lives on main thread

        root = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(root)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.transcript = QtWidgets.QTextBrowser(root)
        self.transcript.setOpenExternalLinks(True)
        layout.addWidget(self.transcript, 1)

        self.input = QtWidgets.QTextEdit(root)
        self.input.setPlaceholderText("Ask Claude to inspect, create, or modify the model…  (Ctrl+Enter to send)")
        self.input.setMinimumHeight(160)
        layout.addWidget(self.input)

        row = QtWidgets.QHBoxLayout()
        self.status_label = QtWidgets.QLabel("ready", root)
        self.status_label.setStyleSheet("color: gray;")
        row.addWidget(self.status_label, 1)
        self.clear_btn = QtWidgets.QPushButton("Clear", root)
        self.clear_btn.clicked.connect(self._clear)
        row.addWidget(self.clear_btn)
        self.continue_btn = QtWidgets.QPushButton("Continue", root)
        self.continue_btn.setEnabled(False)
        self.continue_btn.setToolTip("Resume the previous task — only enabled after the model hit max iterations.")
        self.continue_btn.clicked.connect(self._continue)
        row.addWidget(self.continue_btn)
        self.cancel_btn = QtWidgets.QPushButton("Cancel", root)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        row.addWidget(self.cancel_btn)
        self.send_btn = QtWidgets.QPushButton("Send", root)
        self.send_btn.setDefault(True)
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.send_btn)
        layout.addLayout(row)

        self.setWidget(root)

        send_sc = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Return"), self.input)
        send_sc.activated.connect(self._send)

        self._append_system("Agentic ready. Set ANTHROPIC_API_KEY or configure via Agentic → Preferences.")

    # ------------------- transcript helpers -------------------

    def _cursor_at_end(self) -> QtGui.QTextCursor:
        cursor = self.transcript.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        return cursor

    def _append_system(self, text: str):
        self.transcript.append(f"<span style='color:gray'>· {_escape(text)}</span>")

    def _append_user(self, text: str):
        self.transcript.append(f"<p><b>You:</b> {_escape(text).replace(chr(10), '<br>')}</p>")

    def _append_tool_note(self, text: str, color: str = "#888"):
        self.transcript.append(f"<span style='color:{color}'>· {_escape(text)}</span>")

    def _append_error(self, text: str):
        self.transcript.append(f"<pre style='color:#c33'>{_escape(text)}</pre>")

    def _open_assistant_paragraph(self):
        if self._streaming_open:
            return
        cursor = self._cursor_at_end()
        cursor.insertHtml("<p><b>Claude:</b> </p>")
        # position cursor just before the closing </p>: easier — append subsequent text
        # via insertText which adds to current block. Move back into the paragraph:
        cursor.movePosition(QtGui.QTextCursor.End)
        self.transcript.setTextCursor(cursor)
        self._streaming_open = True

    def _close_assistant_paragraph(self):
        self._streaming_open = False

    def _stream_text(self, delta: str):
        if not delta:
            return
        self._open_assistant_paragraph()
        cursor = self._cursor_at_end()
        cursor.insertText(delta)
        self.transcript.setTextCursor(cursor)
        self.transcript.ensureCursorVisible()

    # ------------------- actions -------------------

    def _clear(self):
        if self._thread is not None:
            return
        self._history.clear()
        self.transcript.clear()
        self._streaming_open = False
        self._append_system("conversation cleared")

    def _send(self, text: str | None = None, append_to_transcript: bool = True):
        if self._thread is not None:
            return
        if text is None:
            text = self.input.toPlainText().strip()
            if not text:
                return
            self.input.clear()
        if append_to_transcript:
            self._append_user(text)
        self.send_btn.setEnabled(False)
        self.continue_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status_label.setText("starting…")
        self._streaming_open = False

        self._cancel_event = threading.Event()
        self._thread = QtCore.QThread(self)
        self._worker = _AgentWorker(text, self._history, self._cancel_event, self._dispatcher)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.text_delta.connect(self._stream_text)
        self._worker.assistant_done.connect(self._close_assistant_paragraph)
        self._worker.tool_start.connect(self._on_tool_start)
        self._worker.tool_result.connect(self._on_tool_result)
        self._worker.status.connect(self._on_status)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    def _continue(self):
        if self._thread is not None or not self._history:
            return
        self._append_system("continuing previous task")
        self._send(
            "Continue from where you left off. Pick up the plan you were executing; "
            "do not restart from scratch.",
            append_to_transcript=False,
        )

    def _cancel(self):
        if self._cancel_event is not None:
            self._cancel_event.set()
        self.status_label.setText("cancelling…")
        self.cancel_btn.setEnabled(False)

    # ------------------- signal handlers -------------------

    def _on_tool_start(self, name: str, args: Any):
        self._close_assistant_paragraph()
        preview = _preview_args(args)
        self._append_tool_note(f"→ {name}({preview})", color="#6a7")
        self.status_label.setText(f"running {name}…")

    def _on_tool_result(self, name: str, result: Any, is_error: bool):
        if is_error:
            self._append_error(f"{name} failed:\n{result}")
        else:
            self._append_tool_note(f"✓ {name}", color="#6a7")

    def _on_status(self, msg: str):
        self.status_label.setText(msg)

    def _on_finished(self, result: AgentResult):
        self._close_assistant_paragraph()
        if result.error:
            self._append_error(result.error)
        if result.cancelled:
            self._append_system("cancelled by user")
        self.status_label.setText(
            f"ready · {result.turns} turn(s), {result.tool_calls} tool call(s)"
            + (" · cancelled" if result.cancelled else "")
        )
        self.send_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.continue_btn.setEnabled(result.error == "max_iterations" and not result.cancelled)
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread = None
            self._worker = None
            self._cancel_event = None


def _preview_args(args: Any, limit: int = 80) -> str:
    import json as _json

    try:
        s = _json.dumps(args, default=str)
    except Exception:
        s = str(args)
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    return s


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def show_chat_panel():
    global _PANEL_INSTANCE
    main_window = FreeCADGui.getMainWindow()
    if _PANEL_INSTANCE is None:
        _PANEL_INSTANCE = ChatPanel(main_window)
        main_window.addDockWidget(Qt.RightDockWidgetArea, _PANEL_INSTANCE)
    _PANEL_INSTANCE.show()
    _PANEL_INSTANCE.raise_()
    return _PANEL_INSTANCE
