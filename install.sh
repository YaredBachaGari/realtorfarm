#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if command -v uv >/dev/null 2>&1; then
  uv venv --clear .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  uv pip install -e '.[dev]'
else
  "$PYTHON_BIN" -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade pip
  python -m pip install -e '.[dev]'
fi

python -m pytest -q
echo "RealtorFarm installed. Activate with: source .venv/bin/activate"
