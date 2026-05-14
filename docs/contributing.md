# Contributing

This page is for people who want to improve MkPFS itself.

## Before you start

- Use `uv` for all Python dependency and environment work.
- Keep changes small and focused.
- Run the project checks before you open a pull request.

## Common tasks

```bash
uv sync --group dev
python scripts/sync_docs_sources.py
uv run --frozen pytest
uv run --frozen ruff format .
uv run --frozen ruff check .
uv run mkdocs build --strict
```

## Docs changes

If you add or update knowledge-base content, keep the canonical source under `related-projects/` and resync the docs tree before building.
