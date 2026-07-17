#!/usr/bin/env bash
# IMP-13: create/update venv for operator + tests
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="${RC_VENV:-$ROOT/.venv}"
PY="${PYTHON_BIN:-python3}"
"$PY" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -q -U pip
pip install -q -r "$ROOT/requirements.txt"
echo "venv ready: $VENV"
echo "export PYTHON_BIN=$VENV/bin/python"
