"""Qt compatibility shim.

FreeCAD 1.0 ships PySide2, 1.1+ is moving toward PySide6. Import whichever is present
and re-export the handful of Qt names the addon uses.
"""

try:
    from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore

    QT_VERSION = 6
except ImportError:  # pragma: no cover - version-specific
    from PySide2 import QtCore, QtGui, QtWidgets  # type: ignore

    QT_VERSION = 5

Qt = QtCore.Qt
Signal = QtCore.Signal
QThread = QtCore.QThread

__all__ = ["QtCore", "QtGui", "QtWidgets", "Qt", "Signal", "QThread", "QT_VERSION"]
