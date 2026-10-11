#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root/services/api"

if [[ ! -x .venv/bin/python ]]; then
  uv venv --python 3.12 .venv
  uv pip install -e ".[dev]" --python .venv/bin/python
fi

.venv/bin/ruff check .
.venv/bin/mypy app
.venv/bin/lint-imports
.venv/bin/python -m pytest -q

cd "$root/apps/web"
npx eslint .
