"""Platform dispatch for monitor detection.

Call :func:`detect` rather than importing a back end directly.
"""

from __future__ import annotations

import sys

from .model import DetectionResult, MonitorInfo, ScreenInfoStub

__all__ = ["DetectionResult", "MonitorInfo", "ScreenInfoStub", "detect", "screens_from_qt"]


def screens_from_qt() -> list[ScreenInfoStub]:
    """Snapshot the live QScreen list into plain stubs.

    Must be called from the GUI thread, since QScreen objects are not safe to
    read from anywhere else.
    """
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return []
    return [
        ScreenInfoStub(
            name=screen.name(),
            width=screen.geometry().width(),
            height=screen.geometry().height(),
            dpi=float(screen.logicalDotsPerInch()),
        )
        for screen in QApplication.screens()
    ]


def detect(screens=None) -> DetectionResult:
    """Detect monitors using the back end for the running platform."""
    if sys.platform == "win32":
        from . import monitors_windows as backend
    else:
        from . import monitors_linux as backend
    return backend.detect(screens or [])