"""Transaction helper so every Claude tool call is one undo step."""
from __future__ import annotations

from contextlib import contextmanager

import FreeCAD


@contextmanager
def transaction(label: str):
    doc = FreeCAD.ActiveDocument
    if doc is None:
        yield None
        return
    doc.openTransaction(f"Agentic: {label}")
    try:
        yield doc
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
