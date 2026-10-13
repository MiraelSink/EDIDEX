#!/usr/bin/env bash
# =============================================================================
#  EDIMETER - compilation de l'executable Linux
#
#  Produit : dist/EDIMETER  (~53 Mo, autonome)
#
#  Usage :
#     linux/build.sh            compile et conserve .venv
#     linux/build.sh --clean    compile puis supprime .venv (~54 Mo sur disque)
#
#  Prerequis systeme (verifies ici, non installes automatiquement) :
#     sudo apt install binutils libpython3.13
#         binutils    fournit objdump, utilise par PyInstaller
#         libpython3  bibliotheque partagee Python, necessaire au bootloader
# =============================================================================

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
VPY="$ROOT/.venv/bin/python"
NAME="EDIMETER"
LOG="$ROOT/linux/build.log"
CLEAN=0
[ "${1:-}" = "--clean" ] && CLEAN=1

say()  { printf '\033[32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m==>\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31m*** ECHEC :\033[0m %s\n\n' "$*" >&2; exit 1; }

: > "$LOG"

# --- Prerequis --------------------------------------------------------------
[ -x "$VPY" ] || die "Le virtualenv est absent ou PyInstaller manque.
    Lancez d'abord : linux/setup.sh"

command -v objdump >/dev/null 2>&1 || die "objdump est introuvable (paquet binutils).
    sudo apt install binutils"

# PyInstaller a besoin de la bibliotheque partagee de Python. Toutes les
# distributions ne l'installent pas : python3-minimal ne suffit pas.
PY_SONAME="$("$VPY" -c 'import sysconfig; print(sysconfig.get_config_var("INSTSONAME") or "")')"
if [ -n "$PY_SONAME" ]; then
    if ! "$VPY" -c "import ctypes,sys; ctypes.CDLL(sys.argv[1])" "$PY_SONAME" 2>/dev/null; then
        die "La bibliotheque partagee Python '$PY_SONAME' est absente.
    PyInstaller ne peut pas construire l'executable sans elle.
        sudo apt install libpython${PY_SONAME%%.so*}"
    fi
fi

# --- Nettoyage du cache precedent -----------------------------------------
say "Nettoyage du cache precedent..."
rm -rf "$ROOT/build"

# --- Compilation ------------------------------------------------------------
say "Compilation de $NAME (2 a 5 minutes)..."
# PySide6 rend le binaire volumineux car Qt est embarque. Les modules Qt
# inutiles sont exclus ci-dessous.
"$VPY" -m PyInstaller \
    --noconfirm \
    --onefile \
    --windowed \
    --name "$NAME" \
    --distpath "$ROOT/dist" \
    --workpath "$ROOT/build" \
    --specpath "$ROOT/build" \
    --paths "$ROOT" \
    --exclude-module tkinter \
    --exclude-module unittest \
    --exclude-module pydoc \
    --exclude-module PyQt5 \
    --exclude-module PyQt6 \
    --exclude-module PySide2 \
    --exclude-module numpy \
    --exclude-module scipy \
    --exclude-module matplotlib \
    --exclude-module setuptools \
    --exclude-module pip \
    --hidden-import PySide6.QtCore \
    --hidden-import PySide6.QtGui \
    --hidden-import PySide6.QtWidgets \
    "$ROOT/run.py" 2>&1 | tee -a "$LOG" | tail -5

[ -x "$ROOT/dist/$NAME" ] || die "dist/$NAME est absent alors que PyInstaller a reussi."

# --- Nettoyage --------------------------------------------------------------
say "Nettoyage..."
rm -rf "$ROOT/build"
find "$ROOT" -name __pycache__ -type d -not -path "$ROOT/.venv/*" \
    -exec rm -rf {} + 2>/dev/null || true
say "Cache PyInstaller et __pycache__ supprimes."

# --- Nettoyage optionnel du virtualenv --------------------------------------
if [ "$CLEAN" -eq 1 ]; then
    say "Suppression de .venv demandee par --clean..."
    rm -rf "$ROOT/.venv"
    say ".venv supprime."
    echo
    echo "    Pour recompiler, relancez d'abord linux/setup.sh"
    echo "    (retelechargement de PySide6, environ 90 Mo)."
else
    say ".venv conserve. Utilisez --clean pour le supprimer apres coup."
fi

# --- Bilan ------------------------------------------------------------------
echo
say "Termine : dist/$NAME"
ls -lh "$ROOT/dist/$NAME" | awk '{print "    taille : " $5}'
du -sh "$ROOT" | awk '{print "    dossier total : " $1}'
echo
echo "Le binaire est autonome : aucune installation n'est requise sur la"
echo "machine cible. Testez-le avec : dist/$NAME"
echo
echo "Journal : $LOG"