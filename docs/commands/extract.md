# `extract`

Extract logical files from a PFS image into a destination directory.

## Synopsis

```bash
mkpfs extract --image ./output.ffpfs --out ./extracted/
```

## Useful options

- `--overwrite`: overwrite existing files in the destination.
- `--progress`: show progress during extraction.

## Notes

Extraction preserves the logical tree layout found in the image and returns a structured report when run programmatically via the library API.
