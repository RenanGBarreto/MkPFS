# 📦 MkPFS: Make PFS

`mkpfs` is a Python library for working with unsigned PFS (PlayStation File System) image files.

Think of this as a lightweight, installable starting point for PFS tooling: easy to add with `uv` or `pip`, easy to inspect, and ready for the actual image/compression/checksum pipeline as the project grows.

---

<p align="center"> 
  <a href="https://github.com/sponsors/RenanGBarreto" rel="noopener">
    <img alt="Sponsor" src="https://img.shields.io/badge/Support%20the%20Project-Become%20a%20Sponsor-%23EA4AAA?style=for-the-badge&logo=github&logoColor=white" />
  </a>
</p>

<p align="center"><strong>Help the authors to maintain the project.</strong> <br /> <a href="https://github.com/sponsors/RenanGBarreto" rel="noopener">Consider sponsoring development on GitHub Sponsors </a></p>

---

## Table of contents

- [📦 Installation](#-installation)
- [🧪 Usage](#-usage)
- [✨ Examples](#-examples)
- [🛠️ Development](#-development)
- [🏗️ Build](#-build)
- [🔎 How it works](#-how-it-works)
- [📄 Packaging notes](#-packaging-notes)

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

Install from a local checkout while developing with `uv`:

```bash
uv sync
```

Install from a local checkout while developing with `pip`:

```bash
pip install -e .
```

## 🧪 Usage

```python
from mkpfs import hello

print(hello())
```

Expected output:

```text
Hello from mkpfs!
```

## ✨ Examples

### Minimal script

```python
from mkpfs import hello

message = hello()
print(message)
```

### Run the local demo entry point

```bash
python -m mkpfs
```

## 🛠️ Development

Clone the repository with all submodules, including nested submodules inside related projects:

```bash
git clone --recurse-submodules <repository-url>
```

If you already cloned the repository without submodules, initialize everything recursively:

```bash
git submodule update --init --recursive
```

Update the repository and move submodules to the latest commits on their configured default branches:

```bash
git pull
git submodule update --init --recursive --remote
```

The top-level submodules are configured to track each upstream repository's default branch in `.gitmodules`.

Set up the local environment:

```bash
uv sync
uv run pre-commit install
```

Run the checks directly:

```bash
uv run --frozen pytest
uv run --frozen ruff format .
uv run --frozen ruff check .
uv run --frozen ruff check . --fix
```

## 🏗️ Build

Build a source distribution and wheel:

```bash
uv build
```

Check release artifacts before publishing:

```bash
uv run --frozen twine check dist/*
```

## 🔎 How it works

- `src/mkpfs/__init__.py` exports the public API.
- `src/mkpfs/hello.py` currently contains the only public function, `hello()`.
- `src/mkpfs/__main__.py` is the package entry point used by `python -m mkpfs`.
- TODO: document the real PFS image creation, compression, and checksum flow once those APIs exist.

## 📄 Packaging notes

- Metadata lives in `pyproject.toml`.
- The package uses a `src/` layout.
- Generated release artifacts stay out of version control.
- TODO: add publishing steps once release automation exists.
