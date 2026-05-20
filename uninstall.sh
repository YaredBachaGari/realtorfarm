#!/usr/bin/env bash
set -euo pipefail
rm -rf .venv .pytest_cache .ruff_cache build dist *.egg-info src/*.egg-info
echo "Removed local RealtorFarm install artifacts."
