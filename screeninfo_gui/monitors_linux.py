"""Linux monitor detection.

Order of preference:
  1. ``xrandr --verbose`` - gives geometry, millimetre size and the raw EDID of
     every output in one call, needs no root and works on X11 and XWayland.
  2. ``/sys/class/drm/card*-*/edid`` - used when xrandr is unavailable. These
     nodes are often root-only, so failures are reported rather than retried
     with elevation.

Nothing here ever calls sudo or writes outside the user's own session.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from .edid import EdidInfo, parse_edid, parse_edid_hex
from .model import DetectionResult, MonitorInfo

_XRANDR_RE = re.compile(r"^([A-Za-z0-9_.+\-]+)\s+(connected|disconnected)\b(.*)$")
_GEOM_RE = re.compile(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)")
_MM_RE = re.compile(r"(\d+)mm\s*x\s*(\d+)mm")
_REFRESH_RE = re.compile(r"\*?(\d+(?:\.\d+)?)\s*\*?")
_PRIMARY_RE = re.compile(r"\bprimary\b")
_EDID_START_RE = re.compile(r"^\s*EDID:\s*(.*)$")
_HEXLINE_RE = re.compile(r"^\s*([0-9a-fA-F]{16,})\s*$")


def _run_xrandr() -> tuple[str, str | None]:
    if not shutil.which("xrandr"):
        return "", "xrandr introuvable"
    try:
        proc = subprocess.run(
            ["xrandr", "--verbose"],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return "", "xrandr a echoue: %s" % exc
    if proc.returncode != 0 and not proc.stdout:
        return "", "xrandr a retourne le code %d" % proc.returncode
    return proc.stdout, None


def _parse_xrandr(output: str) -> list[MonitorInfo]:
    """Parse ``xrandr --verbose`` into monitors, keeping EDID hex per output."""
    monitors: list[MonitorInfo] = []
    cur: MonitorInfo | None = None
    hex_lines: list[str] = []
    pending_hex: str | None = None
    order = 0

    def flush() -> None:
        nonlocal cur, hex_lines, pending_hex, order
        if cur is None:
            return
        raw = pending_hex or "".join(hex_lines)
        info: EdidInfo = parse_edid_hex(raw) if raw else EdidInfo()
        _apply_edid(cur, info)
        # Index must reflect position in the output list, not the previous
        # card's count, otherwise every card reports the same "id interne".
        cur.index = order
        monitors.append(cur)
        order += 1
        cur, hex_lines, pending_hex = None, [], None

    for line in output.splitlines():
        m = _XRANDR_RE.match(line)
        if m and not line[:1].isspace():
            flush()
            name, state, rest = m.group(1), m.group(2), m.group(3)
            if state != "connected":
                cur = None
                continue
            cur = MonitorInfo(model=name, source="xrandr")
            geom = _GEOM_RE.search(rest)
            if geom:
                cur.resolution = "%s x %s" % (geom.group(1), geom.group(2))
                cur.position = "+%s+%s" % (geom.group(3), geom.group(4))
            cur.is_primary = bool(_PRIMARY_RE.search(rest))
            mm = _MM_RE.search(rest)
            # "0mm x 0mm" means the output exposes no physical size, not that
            # the panel is zero-sized; leave it unknown so the DPI fallback runs.
            if mm and int(mm.group(1)) > 0 and int(mm.group(2)) > 0:
                cur.width_in = int(mm.group(1)) / 25.4
                cur.height_in = int(mm.group(2)) / 25.4
                cur.size_source = "EDID"
            continue

        if cur is None:
            continue

        ed = _EDID_START_RE.match(line)
        if ed:
            pending_hex = ed.group(1).strip()
            continue
        hx = _HEXLINE_RE.match(line)
        if hx and pending_hex is not None:
            pending_hex += hx.group(1)
    flush()

    # Some compositors omit the "primary" marker entirely; the first connected
    # output is then the primary one by convention.
    if monitors and not any(m.is_primary for m in monitors):
        monitors[0].is_primary = True
    return monitors


def _apply_edid(monitor: MonitorInfo, info: EdidInfo) -> None:
    """Overlay parsed EDID onto a monitor, keeping richer existing values.

    ``monitor.model`` starts out as the xrandr connector name (e.g. "DP-1"),
    which identifies the port rather than the panel, so it is only kept when
    EDID turned out to be unreadable.
    """
    if not info.valid:
        return

    monitor.vendor_code = info.vendor_id
    monitor.edid_hex = info.raw_hex
    if info.display_name:
        monitor.display_name = info.display_name

    # The manufacturer ID names whoever built the panel, which is often not
    # the brand that sold the monitor. The name descriptor usually does.
    named_brand = info.brand_from_name
    monitor.brand = named_brand or info.brand
    if named_brand and info.brand and named_brand.lower() != info.brand.lower():
        monitor.vendor_code = "%s (%s)" % (named_brand, info.vendor_id)

    monitor.model = info.display_name or (
        "Modele %s" % info.product_code if info.product_code else "")
    if info.serial:
        monitor.serial = info.serial

    # Basic display parameters (cm) win; the timing descriptor (mm) is the
    # fallback and is kept visible when the two disagree.
    if info.size_h_cm and info.size_v_cm:
        monitor.width_in = info.width_in
        monitor.height_in = info.height_in
    elif info.dtd_h_mm and info.dtd_v_mm:
        monitor.width_in = info.dtd_width_in
        monitor.height_in = info.dtd_height_in
    if monitor.width_in > 0 and monitor.height_in > 0:
        monitor.size_source = "EDID"
    monitor.alt_size_in = info.dtd_diagonal_in
    monitor.size_conflict = info.size_conflict


def _read_sysfs_edid() -> list[MonitorInfo]:
    """Fallback: walk /sys/class/drm for raw EDID blobs."""
    monitors: list[MonitorInfo] = []
    base = "/sys/class/drm"
    if not os.path.isdir(base):
        return monitors
    try:
        entries = sorted(os.listdir(base))
    except OSError:
        return monitors
    for entry in entries:
        if "-card" in entry or "write" in entry.lower():
            continue
        path = os.path.join(base, entry, "edid")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as fh:
                blob = fh.read()
        except (OSError, PermissionError):
            continue
        if not blob:
            continue
        mon = MonitorInfo(model=entry, source="EDID sysfs")
        _apply_edid(mon, parse_edid(blob))
        # Some sysfs nodes expose the connector's current mode alongside EDID.
        modes = os.path.join(base, entry, "modes")
        try:
            with open(modes) as fh:
                first = fh.readline().strip()
            if first:
                mon.resolution = first.replace("x", " x ")
        except (OSError, PermissionError):
            pass
        monitors.append(mon)
    return monitors


def _apply_dpi_estimate(monitors: list[MonitorInfo], screens) -> None:
    """Fill in missing sizes from Qt's logical DPI.

    This is a guess and is labelled "estimé" in the UI, so it only runs for
    monitors whose EDID size was absent. Screens are matched to monitors by
    order, since Qt exposes no connector name on every platform.
    """
    if not screens:
        return
    by_res = {}
    for screen in screens:
        by_res.setdefault((screen.width, screen.height), []).append(screen)
    for mon in monitors:
        if mon.size_source:
            continue
        try:
            w, h = (int(p) for p in mon.resolution.split(" x "))
        except (ValueError, AttributeError):
            continue
        candidates = by_res.get((w, h))
        if not candidates:
            continue
        screen = candidates.pop(0)
        dpi = screen.logicalDotsPerInch()
        if dpi > 0:
            mon.width_in = w / dpi
            mon.height_in = h / dpi
            mon.size_source = "estimé"


def _is_wsl() -> bool:
    """True under WSL1/WSL2, where monitors are virtual and carry no EDID."""
    if os.path.exists("/proc/sys/fs/binfmt_misc/WSLInterop"):
        return True
    try:
        with open("/proc/version", "r") as fh:
            return "microsoft" in fh.read().lower()
    except OSError:
        return False


def _explain_missing_identity(result: DetectionResult) -> None:
    """Say *why* brand and serial are unavailable instead of leaving a blank.

    On WSL the outputs are RDP sessions created by WSLg; the physical panel's
    EDID lives on the Windows host and is never forwarded, so no amount of
    retrying here will reveal it.
    """
    missing = [m for m in result.monitors
               if not m.brand or not m.serial]
    if not missing:
        return
    if _is_wsl():
        result.warnings.append(
            "Marque et numero de serie indisponibles : cette session WSL "
            "utilise des ecrans virtuels WSLg, dont l'EDID du moniteur "
            "physique n'est pas transmis. Lancez l'application sous Windows "
            "ou sur une session Linux native pour lire ces informations."
        )
    elif result.method == "xrandr":
        result.warnings.append(
            "xrandr ne publie aucun bloc EDID pour ces sorties : certains "
            "cables, hubs USB-C et docks masquent l'EDID. Verifiez avec "
            "xrandr --verbose | grep -A3 EDID."
        )


def _monitors_from_screens(screens) -> list[MonitorInfo]:
    """Last resort: one row per Qt screen, sized from its logical DPI.

    Qt knows a screen exists even when no EDID can be read (Wayland without
    XWayland, WSLg, some VMs). Reporting an estimated size beats reporting
    nothing; every field stays labelled "estimé" or "Non disponible".
    """
    if not screens:
        return []
    out = []
    for i, screen in enumerate(screens):
        mon = MonitorInfo(
            index=i,
            model=screen.name or "Ecran %d" % (i + 1),
            resolution="%d x %d" % (screen.width, screen.height),
            is_primary=(i == 0),
            source="Qt (estimation)",
        )
        dpi = screen.logicalDotsPerInch()
        if dpi > 0:
            mon.width_in = screen.width / dpi
            mon.height_in = screen.height / dpi
            mon.size_source = "estimé"
        out.append(mon)
    return out


def detect(screens=None) -> DetectionResult:
    """Detect every monitor on Linux. ``screens`` is a QScreen snapshot list."""
    result = DetectionResult()

    output, err = _run_xrandr()
    monitors = _parse_xrandr(output) if output else []
    if monitors:
        result.monitors = monitors
        result.method = "xrandr"
    else:
        if err:
            result.warnings.append(err)
        sysfs = _read_sysfs_edid()
        if sysfs:
            result.monitors = sysfs
            result.method = "EDID sysfs"

    if not result.monitors:
        fallback = _monitors_from_screens(screens)
        if not fallback:
            result.method = "indisponible"
            result.warnings.append(
                "Aucun ecran vu par Qt et aucun EDID lisible."
            )
            return result
        result.monitors = fallback
        result.method = "Qt (estimation)"
        result.warnings.append(
            "Aucun EDID accessible : marque et numero de serie sont "
            "inconnus, la taille est une estimation basee sur le DPI."
        )
        _explain_missing_identity(result)
        return result

    _apply_dpi_estimate(result.monitors, screens)
    _explain_missing_identity(result)
    return result