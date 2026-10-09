"""Cross-platform entry point for Monitor_Detection.

Kept separate from the package so that PyInstaller can be pointed at a single
script and so the package stays importable for tests.
"""

from __future__ import annotations

import multiprocessing
import sys


def _preflight() -> list[str]:
    """Report missing shared libraries before Qt aborts cryptically.

    Qt links libGL, libxcb and friends at import time. When one is absent the
    process dies with "Could not load the Qt platform plugin", which suggests
    reinstalling the application even though the real cause is a missing system
    package. Naming the library is far more actionable.
    """
    import ctypes
    import sys

    if sys.platform != "linux":
        return []

    # Probe the libraries Qt's xcb/wayland plugins actually dlopen.
    candidates = [
        "libGL.so.1", "libEGL.so.1", "libxkbcommon.so.0",
        "libfontconfig.so.1", "libdbus-1.so.3", "libxcb-cursor.so.0",
        "libxcb-icccm.so.4", "libxcb-image.so.0", "libxcb-keysyms.so.1",
        "libxcb-render-util.so.0", "libxcb-shape.so.0", "libxcb-xinerama.so.0",
        "libxcb-util.so.1", "libxkbcommon-x11.so.0",
        "libwayland-client.so.0",
    ]
    # Wayland-only libraries: their absence disables that backend but Qt
    # happily falls back to X11, so they must not block startup.
    optional = ["libwayland-cursor.so.0", "libwayland-egl.so.1"]

    def load(name):
        try:
            ctypes.CDLL(name)
            return True
        except OSError:
            return False

    missing = [n for n in candidates if not load(n)]
    soft = [n for n in optional if not load(n)]

    if not missing:
        if soft:
            sys.stderr.write(
                "\nNote : %s absent(s), le backend Wayland sera ignore "
                "(X11 sera utilise).\n\n" % ", ".join(soft)
            )
        return []

    # Map library sonames to the Debian/Ubuntu package that ships them.
    packages = []
    for soname in missing:
        pkg = _deb_package_for(soname)
        if pkg and pkg not in packages:
            packages.append(pkg)

    sys.stderr.write(
        "\nMonitor_Detection ne peut pas demarrer : bibliotheques systeme "
        "manquantes\n%s\n\n"
        "Installez-les avec :\n  sudo apt install %s\n\n"
        "Ce n'est pas un probleme de l'application : Qt a besoin de ces "
        "bibliotheques graphiques de base.\n"
        % ("\n".join("  - %s" % m for m in missing),
           " ".join(packages) if packages else "(voir la liste ci-dessus)")
    )
    return missing


def _deb_package_for(soname: str) -> str | None:
    """Best-effort soname -> Debian package name."""
    table = {
        "libGL.so.1": "libgl1",
        "libEGL.so.1": "libegl1",
        "libxkbcommon.so.0": "libxkbcommon0",
        "libxkbcommon-x11.so.0": "libxkbcommon-x11-0",
        "libfontconfig.so.1": "libfontconfig1",
        "libdbus-1.so.3": "libdbus-1-3",
        "libxcb-cursor.so.0": "libxcb-cursor0",
        "libxcb-icccm.so.4": "libxcb-icccm4",
        "libxcb-image.so.0": "libxcb-image0",
        "libxcb-keysyms.so.1": "libxcb-keysyms1",
        "libxcb-render-util.so.0": "libxcb-render-util0",
        "libxcb-shape.so.0": "libxcb-shape0",
        "libxcb-xinerama.so.0": "libxcb-xinerama0",
        "libxcb-util.so.1": "libxcb-util1",
        "libwayland-client.so.0": "libwayland-client0",
        "libwayland-cursor.so.0": "libwayland-cursor0",
    }
    return table.get(soname)


def main() -> int:
    # Required before anything else when frozen: without it a one-file build
    # re-runs the app in a child process instead of showing the window.
    multiprocessing.freeze_support()

    missing = _preflight()
    if missing:
        return 1

    from screeninfo_gui.app import main as run
    return run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())