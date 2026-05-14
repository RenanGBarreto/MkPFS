# `create`

Build a PFS image from a folder.

## Synopsis

```bash
mkpfs create --path ./input --output ./output.ffpfs
```

## Important options

- `--compress` / `--no-compress`: enable or disable per-file compression.
- `--threshold-gain`: keep compression only when the gain reaches the configured percentage.
- `--block-size`: select a power-of-two block size or use `auto`.
- `--version`: choose the PS4 or PS5 profile.
- `--inode-bits`: build 32-bit or 64-bit inode layouts.
- `--case-sensitive` / `--case-insensitive`: set the filesystem case behavior.
- `--signed`: build a signed image layout.
- `--verify`: run a post-create check after writing the image.

## Notes

The current implementation normalizes the block size, validates the CPU count, and prints a build summary after image generation.
