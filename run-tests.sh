#!/bin/bash
# Run Tests locally

# Exit immediately if a command exits with a non-zero status including undefined variables and errors in pipelines
set -euo pipefail

# Install dependencies
uv sync

# Install pre-commit hooks
git config --unset-all core.hooksPath
uv run pre-commit install --overwrite

# Run formatting and linting (automatically runs on commit)
uv run ruff format .

# Auto Fix
uv run ruff check . --fix

# Run tests
uv run pytest
