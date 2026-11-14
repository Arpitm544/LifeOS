#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 9), "LifeOS requires Python 3.9+"'
"$PYTHON_BIN" -m venv .venv

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[test]'

echo "LifeOS backend installed. Run: .venv/bin/python -m uvicorn app.main:app --reload"
