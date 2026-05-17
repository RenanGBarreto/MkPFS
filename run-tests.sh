#!/usr/bin/env bash
set -euo pipefail

# Ensure .venv is activated (unless SKIP_VENV): python3 must resolve to mkpfs/.venv/bin/python3
# Set SKIP_VENV=1 to skip activating the venv
if [ -z "${SKIP_VENV:-}" ]; then
  pybin=$(which python3 2>/dev/null)
  if [[ ! "$pybin" =~ mkpfs/.venv/bin/python3$ ]]; then
    source .venv/bin/activate || { echo '[run-tests] ERROR: Could not activate .venv'; exit 1; }
  fi
fi

uv sync

# Install pre-commit hooks
git config --unset-all core.hooksPath || true
uv run pre-commit install --overwrite

# Run formatting and linting (automatically runs on commit)
uv run ruff format .

# Auto Fix
uv run ruff check . --fix

# Prepare and validate documentation site (optional)
# Set SKIP_DOCS=1 to skip syncing and building the documentation
if [ -z "${SKIP_DOCS:-}" ]; then
  echo "[run-tests] Syncing and validating documentation (set SKIP_DOCS=1 to skip)"
  python3 scripts/sync_docs_sources.py
  # Ensure dev dependencies (mkdocs, theme) are available for the build
  uv sync --group dev --frozen
  # Build the docs in strict mode to fail on broken links/config
  uv run mkdocs build --strict
else
  echo "[run-tests] SKIP_DOCS is set; skipping docs sync and mkdocs build"
fi

uv run --frozen pytest
