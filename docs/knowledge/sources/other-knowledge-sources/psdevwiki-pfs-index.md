# PSDevWiki PFS Index (Implementation-Focused)

Source URL:
- https://www.psdevwiki.com/ps4/PFS

Local raw snapshot:
- [psdevwiki-pfs.html](psdevwiki-pfs.html)

Link inventories extracted from snapshot:
- [psdevwiki-pfs-links.txt](psdevwiki-pfs-links.txt)
- [psdevwiki-pfs-hrefs.txt](psdevwiki-pfs-hrefs.txt)

Archived on:
- 2026-03-31

## Why this matters

PFS (Pseudo/PlayStation File System) is the filesystem used for PS4 game/save content containers. This page provides core structure needed to build compatible `.ffpfs` images.

## Core spec points from the page

### Filesystem overview
- PFS is UFS-like.
- Block size is configurable via header.
- Typical values called out:
  - game data: 64 KiB
  - save data: 32 KiB
- Block size constraints:
  - minimum 4 KiB
  - maximum 32 MiB
  - must be power-of-two

### Main PFS sections
- Header (superblock)
- Inode blocks
- Directory blocks
- Data blocks

### Header/Superblock fields (key offsets)
- `0x00` version (8 bytes)
  - page states 1 for PS4, 2 for PS5
- `0x08` format/magic (8 bytes)
  - value shown: 20130315
- `0x1C` mode (2 bytes)
  - bit 0: signed/unsigned
  - bit 1: 32/64-bit inode mode
  - bit 2: encrypted
  - bit 3: case-insensitive
- `0x20` blocksz (4 bytes)
- `0x30` ndinode (8 bytes)
- `0x38` ndblock (8 bytes)
- `0x40` ndinodeblock (8 bytes)
- `0x48` superroot_ino (8 bytes)

### Inodes
- Inode table starts at block 1 (second block).
- Inode records do not cross block boundaries.
- 4 inode types exist; mode bits choose format.
- Common practical case noted: unsigned 32-bit inode mode.

Inode fields called out include:
- mode, nlink, flags
- size, size_compressed
- timestamps (4x64-bit + 4x32-bit ns fields)
- uid/gid
- blocks
- direct block pointers (12)
- indirect block pointers (5)

### Dirents
- Directory data is a sequence of dirents.
- 8-byte alignment.
- Fields:
  - ino
  - type
  - namelen
  - entsize
  - name (+ null terminator)
- Types:
  - 2 file
  - 3 directory
  - 4 dot
  - 5 dotdot

### Root discovery
- Tree starts at superroot (index from `superroot_ino`).
- Real filesystem root is `uroot` inside superroot.
- superroot also contains `flat_path_table`.

### flat_path_table
- Sorted mapping of filename hash -> inode value.
- Hash function shown uses case-insensitive uppercase conversion and multiplier 31.

### Encryption note
- Page states encrypted PFS uses XTS-AES-128.
- Keys are derived from PKG IMAGE_KEY (game) or sealed key paths (save).
- Encryption starts at second PFS block (noted with TODO/verify language on page).

## Important links from the PFS page (curated)

Primary related pages:
- https://www.psdevwiki.com/ps4/PKG_files
- https://www.psdevwiki.com/ps4/PKG#Tools
- https://www.psdevwiki.com/ps4/Sealedkey_/_pfsSKKey
- https://www.psdevwiki.com/ps4/PFS#Encryption
- https://www.psdevwiki.com/ps4/PFS#flat_path_table

Supporting references cited on the page:
- https://en.wikipedia.org/wiki/UFS
- https://en.wikipedia.org/wiki/Inode_pointer_structure
- https://www.google.com/patents/EP2878348A1?cl=en

Pinned revision link captured from page:
- https://www.psdevwiki.com/ps4/index.php?title=PFS&oldid=296886

## Implementation notes for our future .ffpfs generator

1. Preserve header semantics exactly (version/magic/mode/blocksz counts).
2. Keep inode and dirent alignment and sizing strict (8-byte dirent alignment, inode-per-block constraints).
3. Build superroot correctly with `uroot` and `flat_path_table`.
4. Use flat_path_table hash behavior exactly (uppercase + `hash = c + 31 * hash`).
5. Keep encryption path modular because keys depend on package context.
6. Validate against the pinned revision and our local HTML snapshot before finalizing writer logic.

## Trust level and caution

- PSDevWiki is reverse-engineering documentation; treat as strong reference but verify against real samples and tool behavior (LibOrbisPkg / ShadowMountPlus).
- Where page says TODO/uncertain, prefer empirical validation with test images.
