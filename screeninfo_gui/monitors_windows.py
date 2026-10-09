"""Windows monitor detection.

Design note: the previous draft tried to reach WMI through raw COM ctypes. That
path needs `win32com`/a COM vtable dance for no real gain, so it was replaced by
two mechanisms that need nothing beyond the standard library:

  1. **Registry EDID.** Windows already caches every monitor's 128-byte EDID
     under
     ``HKLM\\SYSTEM\\CurrentControlSet\\Enum\\DISPLAY\\<MFR><MODEL>\\<instance>\\
     Device Parameters\\EDID``.
     Reading it with `winreg` is a plain read of a public key - no elevation,
     no COM, and it yields the exact same fields the Linux back end parses
     (brand, serial, physical size), so `edid.py` is shared unchanged.
  2. **`EnumDisplayMonitors`.** Per-monitor position, resolution and the
     primary flag, which the registry keys do not carry.

If the registry yields nothing (rare, but possible on stripped images or
virtual/VM displays) PowerShell `Get-CimInstance` is used as a last resort.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import sys

from .edid import parse_edid
from .model import DetectionResult, MonitorInfo

if sys.platform == "win32":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
else:  # allows the module to be imported for tests on Linux
    user32 = None

_ENUM_REGISTRY_KEY = r"SYSTEM\CurrentControlSet\Enum\DISPLAY"


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MONITORINFOEX(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", ctypes.c_wchar * 32),
    ]


MONITORINFOF_PRIMARY = 0x00000001

if sys.platform == "win32":
    _MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
        ctypes.POINTER(RECT), wintypes.LPARAM,
    )
else:  # ctypes has no WINFUNCTYPE off Windows; the module still needs to import
    _MONITORENUMPROC = None


def _enum_displays() -> list[dict]:
    """Return each monitor's device name, pixel rect and primary flag."""
    if user32 is None:
        return []
    found: list[dict] = []

    def callback(hmon, hdc, lprc, lparam):
        info = MONITORINFOEX()
        info.cbSize = ctypes.sizeof(MONITORINFOEX)
        if user32.GetMonitorInfoW(wintypes.HMONITOR(hmon), ctypes.byref(info)):
            found.append({
                "device": info.szDevice,
                "width": info.rcMonitor.right - info.rcMonitor.left,
                "height": info.rcMonitor.bottom - info.rcMonitor.top,
                "left": info.rcMonitor.left,
                "top": info.rcMonitor.top,
                "is_primary": bool(info.dwFlags & MONITORINFOF_PRIMARY),
            })
        return True

    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    if _MONITORENUMPROC is None:
        return []
    proc = _MONITORENUMPROC(callback)
    if not user32.EnumDisplayMonitors(None, None, proc, 0):
        return []
    return found


def _read_registry_edids() -> list[dict]:
    """Collect raw EDID blobs from the registry's DISPLAY enumeration."""
    import winreg

    out: list[dict] = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _ENUM_REGISTRY_KEY)
    except OSError:
        return out

    def walk(key, path, depth):
        if depth > 2:
            return
        try:
            count = winreg.QueryInfoKey(key)[0]
        except OSError:
            return
        names = []
        for i in range(count):
            try:
                names.append(winreg.EnumKey(key, i))
            except OSError:
                continue
        for name in names:
            child_path = path + "\\" + name
            try:
                child = winreg.OpenKey(key, name)
            except OSError:
                continue
            # A 4th-level key is the per-instance key holding "EDID" in a
            # "Device Parameters" subkey.
            try:
                params = winreg.OpenKey(child, "Device Parameters")
            except OSError:
                walk(child, child_path, depth + 1)
                continue
            for value_name in ("EDID", "EdidOverride"):
                try:
                    data, _ = winreg.QueryValueEx(params, value_name)
                except OSError:
                    continue
                if data and len(data) >= 128:
                    out.append({"path": child_path, "edid": bytes(data)})
            walk(child, child_path, depth + 1)

    with root:
        walk(root, _ENUM_REGISTRY_KEY, 0)
    return out


def _resolution_score(display: dict, info) -> int:
    """Rank how well an EDID fits a display: 0 best, 2 worst.

    The registry accumulates an entry for every monitor ever connected, so a
    stale EDID can easily be paired with a live screen and hand it the wrong
    brand, size and serial. Comparing each EDID's preferred resolution against
    what the display is actually running keeps the pairing honest.
    """
    if not info.native_width or not info.native_height:
        return 2
    dw, dh = display["width"], display["height"]
    ew, eh = info.native_width, info.native_height
    if (dw, dh) == (ew, eh):
        return 0
    display_ratio = dw / dh if dh else 0
    edid_ratio = ew / eh if eh else 0
    # A monitor driven above its native size keeps the same aspect ratio, so
    # that is a strong signal; a different ratio is a clear mismatch.
    if display_ratio and edid_ratio:
        if abs(display_ratio - edid_ratio) / display_ratio < 0.05:
            return 1
    return 2


def _match_displays_to_edids(displays: list[dict], edids: list[dict]) -> tuple[list[MonitorInfo], list[str]]:
    """Pair each display with the EDID that best fits it.

    Assigns greedily by score so that a display whose resolution matches one
    EDID exactly claims it before any fallback consumes it. Ties and leftovers
    are reported, because a wrong pairing silently swaps brand, size and serial.
    """
    parsed = [parse_edid(e["edid"]) for e in edids]
    usable = [i for i, info in enumerate(parsed) if info.valid]

    monitors: list[MonitorInfo] = []
    used: set[int] = set()
    ambiguous: list[str] = []

    for i, disp in enumerate(displays):
        mon = MonitorInfo(
            index=i,
            resolution="%d x %d" % (disp["width"], disp["height"]),
            position="+%d+%d" % (disp["left"], disp["top"]),
            is_primary=disp["is_primary"],
            source="Registre EDID",
        )

        free = [x for x in usable if x not in used]
        if not free:
            monitors.append(mon)
            ambiguous.append(disp["device"])
            continue

        scores = [_resolution_score(disp, parsed[x]) for x in free]
        best = min(scores)
        winners = [x for x, s in zip(free, scores) if s == best]
        chosen = winners[0]

        # Only flag genuine doubt. A screen driven above its EDID's native
        # resolution keeps the same aspect ratio, which is normal and not a
        # reason to cry wolf on every single-monitor setup.
        if best > 1 or len(winners) > 1:
            ambiguous.append(disp["device"])
        used.add(chosen)
        _apply_edid(mon, parsed[chosen], edids[chosen])
        monitors.append(mon)

    return monitors, ambiguous


def _apply_edid(monitor: MonitorInfo, info, entry: dict) -> None:
    """Fill a monitor from its EDID, honouring the cm / mm distinction."""
    monitor.vendor_code = info.vendor_id
    monitor.edid_hex = info.raw_hex
    if info.display_name:
        monitor.display_name = info.display_name

    named_brand = info.brand_from_name
    monitor.brand = named_brand or info.brand
    if named_brand and info.brand and named_brand.lower() != info.brand.lower():
        monitor.vendor_code = "%s (%s)" % (named_brand, info.vendor_id)

    monitor.model = info.display_name or (
        "Modele %s" % info.product_code if info.product_code else "")
    if info.serial:
        monitor.serial = info.serial

    if info.size_h_cm and info.size_v_cm:
        monitor.width_in, monitor.height_in = info.width_in, info.height_in
    elif info.dtd_h_mm and info.dtd_v_mm:
        monitor.width_in = info.dtd_width_in
        monitor.height_in = info.dtd_height_in
    if monitor.width_in > 0 and monitor.height_in > 0:
        monitor.size_source = "EDID"
    monitor.alt_size_in = info.dtd_diagonal_in
    monitor.size_conflict = info.size_conflict


def _powershell_fallback() -> list[MonitorInfo]:
    """Last resort: ask CIM for the monitor classes. Read-only, no elevation."""
    import json
    import subprocess

    query = (
        "Get-CimInstance -ClassName WmiMonitorID | "
        "ForEach-Object { "
        "$m = ($_.ManufacturerName | Where-Object { $_ -ne 0 } | "
        "ForEach-Object { [char]$_ }) -join ''; "
        "$s = ($_.SerialNumberID | Where-Object { $_ -ne 0 } | "
        "ForEach-Object { [char]$_ }) -join ''; "
        "[PSCustomObject]@{ Brand = $m; Serial = $s } } | ConvertTo-Json -Compress"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", query],
            capture_output=True, text=True, timeout=25,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return []
        data = json.loads(proc.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    if isinstance(data, dict):
        data = [data]
    out = []
    for i, row in enumerate(data):
        mon = MonitorInfo(index=i, source="WMI (PowerShell)")
        mon.brand = row.get("Brand") or ""
        mon.serial = row.get("Serial") or ""
        out.append(mon)
    return out


def _apply_dpi_estimate(monitors, screens) -> None:
    """Guess any missing size from Qt's logical DPI (labelled "estimé")."""
    if not screens:
        return
    by_res: dict[tuple[int, int], list] = {}
    for screen in screens:
        by_res.setdefault((screen.width, screen.height), []).append(screen)
    for mon in monitors:
        if mon.size_source:
            continue
        try:
            w, h = (int(p) for p in mon.resolution.split(" x "))
        except (ValueError, AttributeError):
            continue
        pool = by_res.get((w, h))
        if not pool:
            continue
        dpi = pool.pop(0).logicalDotsPerInch()
        if dpi > 0:
            mon.width_in = w / dpi
            mon.height_in = h / dpi
            mon.size_source = "estimé"


def detect(screens=None) -> DetectionResult:
    result = DetectionResult()

    displays = _enum_displays()
    edids = _read_registry_edids()

    if edids and displays:
        result.monitors, ambiguous = _match_displays_to_edids(displays, edids)
        result.method = "Registre EDID"
        if ambiguous:
            result.warnings.append(
                "Appairement approximatif pour %d écran(s) identique(s) : %s. "
                "Marque, taille et numéro de série peuvent être permutés."
                % (len(ambiguous), ", ".join(ambiguous))
            )
    elif edids:
        monitors = []
        for i, entry in enumerate(edids):
            mon = MonitorInfo(index=i, source="Registre EDID")
            _apply_edid(mon, parse_edid(entry["edid"]), entry)
            monitors.append(mon)
        result.monitors = monitors
        result.method = "Registre EDID"
        result.warnings.append("EnumDisplayMonitors a échoué, positions inconnues.")
    elif displays:
        monitors = []
        for i, disp in enumerate(displays):
            monitors.append(MonitorInfo(
                index=i, source="EnumDisplayMonitors",
                resolution="%d x %d" % (disp["width"], disp["height"]),
                position="+%d+%d" % (disp["left"], disp["top"]),
                is_primary=disp["is_primary"]))
        result.monitors = monitors
        result.method = "EnumDisplayMonitors"
        result.warnings.append("Aucun EDID dans le registre pour ces écrans.")
    else:
        extra = _powershell_fallback()
        if extra:
            result.monitors = extra
            result.method = "WMI (PowerShell)"
            result.warnings.append("Ni EDID ni EnumDisplayMonitors disponibles.")
        else:
            result.method = "indisponible"
            result.warnings.append("Aucun écran détecté.")
            return result

    for mon in result.monitors:
        if not mon.brand:
            mon.brand = "Inconnue"
    _apply_dpi_estimate(result.monitors, screens)
    return result
