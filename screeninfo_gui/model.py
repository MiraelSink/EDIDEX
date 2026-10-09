"""Platform-independent monitor description shared by the Linux and Windows
back ends and rendered by the GUI."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Shown wherever the EDID/WMI data does not contain a value.
UNAVAILABLE = "Non disponible"


@dataclass
class MonitorInfo:
    """One physical monitor, as far as we could identify it."""

    index: int = 0
    brand: str = ""
    model: str = ""
    serial: str = ""
    width_in: float = 0.0
    height_in: float = 0.0
    size_source: str = ""       # "EDID" | "estimé" | ""
    alt_size_in: float = 0.0    # conflicting figure from the timing descriptor
    size_conflict: bool = False
    vendor_code: str = ""       # raw three-letter EDID manufacturer code
    display_name: str = ""      # EDID monitor name descriptor
    resolution: str = ""        # e.g. "2560 x 1440"
    refresh_hz: str = ""
    position: str = ""          # e.g. "+1920+0"
    is_primary: bool = False
    source: str = ""            # which backend produced this row
    edid_hex: str = ""          # raw EDID, for diagnostics

    @property
    def diagonal_in(self) -> float:
        """Physical diagonal in inches, 0.0 when unknown."""
        if self.width_in <= 0 or self.height_in <= 0:
            return 0.0
        return math.hypot(self.width_in, self.height_in)

    @property
    def size_text(self) -> str:
        if self.width_in <= 0 or self.height_in <= 0:
            return UNAVAILABLE
        return "%.1f x %.1f pouces" % (self.width_in, self.height_in)

    @property
    def size_cm_text(self) -> str:
        if self.width_in <= 0 or self.height_in <= 0:
            return UNAVAILABLE
        return "%.0f x %.0f cm" % (self.width_in * 2.54, self.height_in * 2.54)

    @property
    def diagonal_text(self) -> str:
        d = self.diagonal_in
        return '%.1f"' % d if d > 0 else UNAVAILABLE

    @property
    def brand_text(self) -> str:
        return self.brand or UNAVAILABLE

    @property
    def model_text(self) -> str:
        return self.model or UNAVAILABLE

    @property
    def serial_text(self) -> str:
        return self.serial or UNAVAILABLE

    @property
    def title(self) -> str:
        """Brand plus model, collapsing cleanly when either is missing."""
        parts = [p for p in (self.brand_text, self.model_text) if p != UNAVAILABLE]
        if not parts:
            return "Ecran %d" % (self.index + 1)
        if len(parts) == 1:
            return parts[0]
        return " ".join(parts)

    def as_text(self) -> str:
        """Plain-text summary, one line per field, for clipboard export."""
        lines = [
            "Ecran %d - %s" % (self.index + 1, self.title),
            "  Marque            : %s" % self.brand_text,
            "  Numero de serie   : %s" % self.serial_text,
            "  Diagonale         : %s" % self.diagonal_text,
            "  Taille physique   : %s" % self.size_text,
            "  Resolution        : %s" % (self.resolution or UNAVAILABLE),
        ]
        if self.position:
            lines.append("  Position          : %s" % self.position)
        if self.display_name:
            lines.append("  Nom EDID          : %s" % self.display_name)
        if self.vendor_code:
            lines.append("  Code fabricant    : %s" % self.vendor_code)
        if self.size_conflict and self.alt_size_in:
            lines.append("  Taille (descripteur de timing) : %.1f pouces"
                         % self.alt_size_in)
        if self.edid_hex:
            lines.append("  EDID brut         : %s" % self.edid_hex)
        return "\n".join(lines)


@dataclass
class DetectionResult:
    """Outcome of one detection pass, including how it was obtained."""

    monitors: list[MonitorInfo] = field(default_factory=list)
    method: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class ScreenInfoStub:
    """Screen data detached from Qt.

    Detection runs on a worker thread, where touching QScreen is unsafe, so the
    GUI hands over plain values in this shape. It also lets the detection code
    be unit-tested without a running Qt application.
    """

    name: str = ""
    width: int = 0
    height: int = 0
    dpi: float = 96.0

    def geometry(self):
        """QScreen-compatible accessor returning an object with width/height."""
        return self

    def logicalDotsPerInch(self) -> float:
        return self.dpi