#!/usr/bin/env bash
# =============================================================================
#  EDIMETER - installation de l'environnement de developpement
#
#  Installe PySide6 et PyInstaller dans un virtualenv local (../.venv).
#  Aucun droit administrateur n'est requis : rien n'est écrit hors du dossier
#  du projet, et aucun appel a sudo n'est fait.
#
#  Usage : linux/setup.sh
# =============================================================================

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
VENV="$ROOT/.venv"
LOG="$ROOT/linux/setup.log"
PY="${PYTHON:-python3}"

say()  { printf '\033[32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m==>\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31m*** ECHEC :\033[0m %s\n\n' "$*" >&2
         printf '    Journal : %s\n\n' "$LOG" >&2
         exit 1; }

: > "$LOG"
say "Journal : $LOG"

# --- 1. interpreteur -------------------------------------------------------
command -v "$PY" >/dev/null 2>&1 || die \
    "python3 est introuvable.

    Installez Python 3.9 ou plus :
      https://www.python.org/downloads/

    Sous Debian/Ubuntu :  sudo apt install python3 python3-venv"

if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 9) else 1)'; then
    die "Python 3.9 ou plus est requis.
    Version detectee : $("$PY" -V 2>&1)"
fi
say "Interpreteur : $("$PY" -V 2>&1)"

# --- 2. virtualenv ---------------------------------------------------------
if [ -x "$VENV/bin/python" ]; then
    say "Virtualenv deja present, conserve."
else
    say "Creation du virtualenv..."
    if ! "$PY" -m venv "$VENV" 2>>"$LOG"; then
        warn "venv a echoue, nouvelle tentative sans symlinks..."
        "$PY" -m venv --copies "$VENV" 2>>"$LOG" \
            || die "Creation du virtualenv impossible.
    Sous Debian/Ubuntu :  sudo apt install python3-venv"
    fi
fi

VPY="$VENV/bin/python"
[ -x "$VPY" ] || die "Python du virtualenv introuvable a $VPY"

# --- 3. pip ----------------------------------------------------------------
if ! "$VPY" -m pip --version >/dev/null 2>&1; then
    warn "pip absent du virtualenv, amorcage..."
    if ! "$VPY" -m ensurepip --upgrade >>"$LOG" 2>&1; then
        warn "ensurepip a echoue, recuperation de get-pip.py..."
        tmp="$(mktemp)"
        if command -v curl >/dev/null 2>&1; then
            curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$tmp"
        elif command -v wget >/dev/null 2>&1; then
            wget -q https://bootstrap.pypa.io/get-pip.py -O "$tmp"
        else
            rm -f "$tmp"
            die "ni curl ni wget disponibles pour recuperer get-pip.py."
        fi
        "$VPY" "$tmp" >>"$LOG" 2>&1 || { rm -f "$tmp"; die "get-pip.py a echoue."; }
        rm -f "$tmp"
    fi
fi
say "pip : $("$VPY" -m pip --version | cut -d' ' -f2)"

# --- 4. dependances --------------------------------------------------------
say "Installation de PySide6 et PyInstaller (quelques minutes)..."
"$VPY" -m pip install --upgrade pip >>"$LOG" 2>&1
"$VPY" -m pip install -r "$ROOT/requirements.txt" >>"$LOG" 2>&1 \
    || die "Installation des dependances echouee.
    Verifiez votre connexion internet. Journal : $LOG"

# --- 5. bibliotheques graphiques systeme -----------------------------------
# Qt charge ces bibliotheques avant d'afficher une fenetre. Elles sont
# detectees et signalees, mais pas installees : ce serait une action
# systeme que ce script refuse d'entreprendre a votre place.
missing=()
for lib in libGL.so.1 libEGL.so.1 libxkbcommon.so.0 libfontconfig.so.1 \
           libdbus-1.so.3 libxcb-cursor.so.0 libxcb-icccm.so.4 \
           libxcb-image.so.0 libxcb-keysyms.so.1 libxcb-render-util.so.0 \
           libxcb-shape.so.0 libxcb-xinerama.so.0 libxcb-util.so.1 \
           libwayland-client.so.0; do
    "$VPY" -c "import ctypes,sys; ctypes.CDLL(sys.argv[1])" "$lib" 2>/dev/null \
        || missing+=("$lib")
done
if [ ${#missing[@]} -gt 0 ]; then
    warn "Bibliotheques graphiques systeme manquantes :"
    printf '    - %s\n' "${missing[@]}"
    warn "L'application refusera de demarrer tant qu'elles sont absentes."
    warn "Installez-les vous-meme (aucun sudo de notre part) :"
    printf '    sudo apt install libgl1 libegl1 libxkbcommon0 libxkbcommon-x11-0 \\\n'
    printf '      libfontconfig1 libdbus-1-3 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \\\n'
    printf '      libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 \\\n'
    printf '      libxcb-util1 libwayland-client0\n'
fi

# --- 6. verification -------------------------------------------------------
say "Verification finale..."
"$VPY" "$ROOT/check_env.py" || warn " certaines dependances restent absentes."

say "Termine. Lancez l'application avec : linux/run.sh"
say "Compilez avec :                  linux/build.sh"