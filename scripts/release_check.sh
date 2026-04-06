#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python interpreter not found at $PYTHON_BIN" >&2
  echo "Create the project venv first or set PYTHON_BIN." >&2
  exit 1
fi

cd "$ROOT_DIR"

"$PYTHON_BIN" -m unittest discover -s tests -q

if ! "$PYTHON_BIN" -c "import build" >/dev/null 2>&1; then
  echo "The 'build' package is required for release checks." >&2
  echo "Install it with: $PYTHON_BIN -m pip install build" >&2
  exit 1
fi

rm -rf build dist src/*.egg-info *.egg-info
"$PYTHON_BIN" -m build

echo
echo "Release check passed."
