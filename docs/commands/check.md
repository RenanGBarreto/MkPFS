# `check`

Validate an image structure, contents, and hashes.

## Synopsis

```bash
mkpfs check --image ./output.ffpfs
```

## Useful options

- `--source`: compare the image against a source folder.
- `--expected-crc32`: enforce the cumulative data CRC32.
- `--expected-manifest-sha256`: enforce the manifest digest.
- `--print-tree`: print the parsed tree after the report.

## Notes

`verify` is an alias for `check`.
