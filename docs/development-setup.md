# Development setup

Use this page when you need to work on the codebase or the documentation site locally.

## Environment

```bash
uv sync --group dev
```

## Docs preview

```bash
python scripts/sync_docs_sources.py
uv run mkdocs serve
```

## Validation

```bash
uv run --frozen pytest
uv run --frozen ruff format .
uv run --frozen ruff check .
uv run mkdocs build --strict
```

## Packaging checks

```bash
uv build
uv run --frozen twine check dist/*
```