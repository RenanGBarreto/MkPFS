# Getting started

MkPFS is a command-line tool for building, checking, and listing unsigned PFS images. This page focuses on the shortest path from install to a successful first run.

## Install

```bash
uv sync
```

## Confirm the tool is available

```bash
uv run mkpfs -h
```

The help output should show the `create`, `check`, and `ls` commands.

## Build an image

Create a PFS image from a folder:

```bash
uv run mkpfs create --path ./input --output ./output.ffpfs
```

If you want a dry run first, add `--dry-run` to inspect the layout without writing the file.

## Check the result

Validate the generated image:

```bash
uv run mkpfs check --image ./output.ffpfs
```

You can also compare it against the source tree with `--source ./input`.

## List contents

Print the filesystem tree inside the image:

```bash
uv run mkpfs ls --image ./output.ffpfs
```

## What to read next

- Use [Commands](commands/index.md) for the full CLI reference.
- Use [Knowledge Base](knowledge/index.md) for background on PFS and PKG formats.
- Use [Contributing](contributing.md) if you want to help improve the project.
