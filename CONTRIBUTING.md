# 🤝 Contributing

Thanks for helping improve MkPFS.

This guide is for contributors working on the CLI, library, GUI-facing documentation, packaging, or the research/docs material that supports the project.

## 🚀 Before you start

- Use `uv` for all Python dependency and environment work.
- Keep changes focused and easy to review.
- Run the relevant project checks before opening a pull request.
- Prefer updating existing files instead of creating duplicate docs.

## 🧰 Local setup

```bash
uv sync --group dev
uv run pre-commit install
```

## ✅ Common checks

```bash
uv run --frozen pytest
uv run --frozen ruff format .
uv run --frozen ruff check .
uv build
uv run --frozen twine check dist/*
```

## 📚 Documentation workflow

When you update the docs site or knowledge-base content, keep the canonical source material under `related-projects/` and then resync the docs tree before building.

```bash
python scripts/sync_docs_sources.py
uv run mkdocs build --strict
```

For local preview:

```bash
python scripts/sync_docs_sources.py
uv run mkdocs serve
```

## 🧪 What to update where

- `README.md` — public project overview, badges, screenshots, quick-start messaging, sponsorship links
- `docs/` — user-facing documentation site content
- `related-projects/` — canonical archived sources, summaries, and reference material used by the docs site

If you update technical source summaries or imported reference material, make the change in `related-projects/` first and then sync the docs copy.

## 🔎 Pull request expectations

- Keep pull requests scoped to a clear goal.
- Include updated docs or screenshots when user-facing behavior changes.
- Preserve the current blue visual identity when editing README or docs graphics.
- Do not commit one-off temporary files from `tmp/`.
