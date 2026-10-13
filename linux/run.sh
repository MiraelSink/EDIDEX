#!/usr/bin/env bash
# =============================================================================
#  EDIMETER - lancement de l'application
#
#  Utilise le virtualenv du projet. S'il est absent, lancez d'abord
#  linux/setup.sh.
#
#  Usage : linux/run.sh
# =============================================================================

set -euo pipefail

cd "$(dirname "$0")/.."

VPY=".venv/bin/python"

if [ ! -x "$VPY" ]; then
    cat >&2 <<'EOF'

*** Le virtualenv est absent.

    Attendu : .venv/bin/python

    Lancez d'abord linux/setup.sh pour installer les dependances.

EOF
    exit 1
fi

exec "$VPY" run.py "$@"