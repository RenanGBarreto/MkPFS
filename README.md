# MkPFS

`mkpfs` is the command-line tool for building, checking, and inspecting unsigned PFS images.

The user guide and knowledge base now live in the MkDocs site that is being added to this repository. Use the docs pages for the current command reference, the knowledge-base menu, and the long-form PFS/PKG background material.

## Quick start

Install the local development environment:

```bash
uv sync
```

Inspect the CLI help:

```bash
uv run mkpfs -h
```

Build a PFS image:

```bash
uv run mkpfs create --path ./input --output ./output.ffpfs
```

Validate an image:

```bash
uv run mkpfs check --image ./output.ffpfs
```

List image contents:

```bash
uv run mkpfs ls --image ./output.ffpfs
```

## Documentation workflow

The docs site is rendered with MkDocs and will be published through GitHub Pages after merge to `main`.

For local docs work, sync the reusable knowledge-base sources and then build or serve the site:

```bash
python scripts/sync_docs_sources.py
uv run mkdocs build --strict
uv run mkdocs serve
```

## Development

Run the project checks with:

```bash
uv run --frozen pytest
uv run --frozen ruff format .
uv run --frozen ruff check .
```

Build release artifacts with:

```bash
uv build
uv run --frozen twine check dist/*
```
