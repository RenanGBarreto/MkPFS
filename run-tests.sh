#!/bin/bash
# Run Tests locally

# Exit immediately if a command exits with a non-zero status including undefined variables and errors in pipelines
set -euo pipefail

# Install dependencies
uv sync

# Install pre-commit hooks
git config --unset-all core.hooksPath || true
uv run pre-commit install --overwrite

# Run formatting and linting (automatically runs on commit)
uv run ruff format .

# Auto Fix
uv run ruff check . --fix

# Prepare and validate documentation site (optional)
# Set SKIP_DOCS=1 to skip syncing and building the documentation (useful on CI or when mkdocs
# dependencies are not available locally).
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

# Run tests
uv run pytest
