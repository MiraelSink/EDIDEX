"""Diagnostic check run before install and build.

Prints one line per requirement and exits non-zero if anything required is
missing. Both ``setup.sh`` and ``setup.bat`` call this first so the two
platforms report problems identically.

Read-only: it never installs, never writes and never asks for privileges.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys

MIN_PYTHON = (3, 9)
REQUIRED = ["PySide6"]
BUILD_ONLY = ["PyInstaller"]


def _has(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _pip_version() -> str:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "absent"
    if proc.returncode != 0:
        return "absent"
    return proc.stdout.split()[1] if proc.stdout.split() else "absent"


def main() -> int:
    problems: list[str] = []
    print("Verification de l'environnement - Monitor_Detection")
    print("-" * 52)

    version = ".".join(str(n) for n in sys.version_info[:3])
    ok = sys.version_info[:2] >= MIN_PYTHON
    print("  %-22s %-10s %s" % ("Python", version, "OK" if ok else "TROP ANCIEN"))
    if not ok:
        problems.append("Python %d.%d+ est requis."
                        % (MIN_PYTHON[0], MIN_PYTHON[1]))

    pip = _pip_version()
    has_pip = pip != "absent"
    print("  %-22s %-10s %s" % ("pip", pip, "OK" if has_pip else "ABSENT"))
    if not has_pip:
        problems.append("pip absent - sera installe dans le venv par setup.")

    has_venv = _has("venv") or importlib.util.find_spec("ensurepip") is not None
    print("  %-22s %-10s %s" % ("venv/ensurepip", "present" if has_venv else "absent",
                                 "OK" if has_venv else "ABSENT"))
    if not has_venv:
        problems.append("venv et ensurepip absents: visez python3-venv.")

    for module in REQUIRED:
        present = _has(module)
        print("  %-22s %-10s %s" % (module, "installé" if present else "absent",
                                     "OK" if present else "A INSTALLER"))
        if not present:
            problems.append("%s doit être installé dans le venv." % module)

    for module in BUILD_ONLY:
        present = _has(module)
        print("  %-22s %-10s %s" % (module, "installé" if present else "absent",
                                     "OK" if present else "A INSTALLER (build)"))
        # Not fatal: only needed when building a binary, not to run the app.

    print("-" * 52)
    if problems:
        print("Manquants (%d) :" % len(problems))
        for item in problems:
            print("  - %s" % item)
        return 1
    print("Tout est en place.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())