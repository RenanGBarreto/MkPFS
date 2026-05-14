# 📦 MkPFS: Make PFS

`mkpfs` is a command-line tool for building, checking, and inspecting unsigned PlayStation PFS (PlayStation File System) images.

> Status: pre-alpha. The core PFS workflow is actively being built out.

## Table of contents

- [📦 Installation](#-installation)
- [🧪 Usage](#-usage)
- [✨ Examples](#-examples)
- [🛠️ Development](#-development)
- [🏗️ Build](#-build)
- [📚 Documentation](#-documentation)

---

## 📦 Installation

Install from PyPI with `uv`:

```bash
uv add mkpfs
```

Install from PyPI with `pip`:

```bash
pip install mkpfs
```

## 🧪 Usage

```bash
# Build a PFS image
mkpfs create --path ./input --output ./output.ffpfs

# Validate an image
mkpfs check --image ./output.ffpfs

# List image contents
mkpfs ls --image ./output.ffpfs
```

Run `mkpfs --help` for the full command reference.

## ✨ Examples

### Inspect the CLI help

```bash
mkpfs -h
mkpfs create -h
```

### Run from a local checkout

```bash
uv run mkpfs create --path ./input --output ./output.ffpfs
```

## 🛠️ Development

Set up the local environment:

```bash
uv sync
uv run pre-commit install
```

Run the checks:

```bash
uv run --frozen pytest
uv run --frozen ruff format .
uv run --frozen ruff check .
```

For local docs work, sync the knowledge-base sources and preview the site:

```bash
python scripts/sync_docs_sources.py
uv run mkdocs serve
```

## 🏗️ Build

Build a source distribution and wheel:

```bash
uv build
uv run --frozen twine check dist/*
```

## 📚 Documentation

The full user guide and PFS/PKG knowledge base live in the MkDocs site published to GitHub Pages.
