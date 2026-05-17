#!/usr/bin/env python3
"""Analyze a real PFS image to verify structure assumptions."""

import struct
import sys
from pathlib import Path

PFS_MAGIC = 20130315


def analyze_pfs_header(filepath, read_size=0x1000):
    """Parse and display PFS header information."""
    path = Path(filepath)

    if not path.exists():
        print(f"ERROR: File not found: {filepath}")
        return False

    with open(filepath, "rb") as f:
        data = f.read(read_size)

    if len(data) < 0x48:
        print(f"ERROR: File too small, need at least 0x48 bytes, got {len(data)}")
        return False

    # Parse header fields (matching LibOrbisPkg PfsHeader structure)
    (version,) = struct.unpack_from("<q", data, 0x00)
    (magic,) = struct.unpack_from("<q", data, 0x08)
    (id_field,) = struct.unpack_from("<q", data, 0x10)
    fmode, clean, readonly, rsv = struct.unpack_from("<BBBB", data, 0x18)
    (mode,) = struct.unpack_from("<H", data, 0x1C)
    (unk1,) = struct.unpack_from("<H", data, 0x1E)
    (block_size,) = struct.unpack_from("<I", data, 0x20)
    (nbackup,) = struct.unpack_from("<I", data, 0x24)
    (nblock,) = struct.unpack_from("<q", data, 0x28)
    (dinode_count,) = struct.unpack_from("<q", data, 0x30)
    (ndblock,) = struct.unpack_from("<q", data, 0x38)
    (dinode_block_count,) = struct.unpack_from("<q", data, 0x40)

    print("=" * 70)
    print("PFS Image Analysis")
    print("=" * 70)
    print(f"\nFile: {filepath}")
    print(f"Size: {path.stat().st_size / (1024**3):.2f} GB")

    print("\n[SUPERBLOCK - Offsets 0x00-0x4F]")
    print(f"  Version:           {version}")
    print(f"  Magic:             0x{magic:016X} (expected 0x{PFS_MAGIC:016X})")
    print(f"    Magic Match:     {'✓ YES' if magic == PFS_MAGIC else '✗ NO'}")
    print(f"  ID:                {id_field}")
    print(f"  Fmode:             {fmode}")
    print(f"  Clean:             {clean}")
    print(f"  ReadOnly:          {readonly}")
    print(f"  Rsv:               {rsv}")

    print(f"\n[MODE BITS - Offset 0x1C] = 0x{mode:04X}")
    print(f"  Bit 0 (0x01) Signed:           {bool(mode & 0x01)}")
    print(f"  Bit 1 (0x02) 64-bit Inodes:   {bool(mode & 0x02)}")
    print(f"  Bit 2 (0x04) Encrypted:       {bool(mode & 0x04)}")
    print(f"  Bit 3 (0x08) Case-Insensitive:{bool(mode & 0x08)}")

    print("\n[BLOCK CONFIGURATION]")
    print(f"  Block Size:        {block_size:,} bytes ({block_size // 1024} KiB)")
    print(f"  NBackup:           {nbackup}")
    print(f"  NBlock:            {nblock}")
    print(f"  DinodeCount:       {dinode_count:,}")
    print(f"  Ndblock:           {ndblock:,}")
    print(f"  DinodeBlockCount:  {dinode_block_count:,}")

    if block_size > 0:
        inodes_per_block = block_size // 0xA8  # 0xA8 = 168 bytes per inode (D32)
        print("\n[CALCULATED VALUES]")
        print(f"  Inodes per block:  {inodes_per_block}")
        print(f"  Total inode storage: {dinode_block_count * block_size:,} bytes")
        print(f"  Data block start:  Block {1 + dinode_block_count + 1}")

    print("\n[INODE BLOCK SIGNATURE - Offset 0x50 onwards]")
    # Parse the InodeBlockSig inode structure (D32 format)
    ib_mode, ib_nlink, ib_flags = struct.unpack_from("<HHI", data, 0x50)
    ib_size, ib_size_compressed = struct.unpack_from("<qq", data, 0x56)
    (ib_blocks,) = struct.unpack_from("<I", data, 0x8C)
    ib_db_ptrs = struct.unpack_from("<12i", data, 0x90)

    print(f"  Mode:              0x{ib_mode:04X}")
    print(f"  Nlink:             {ib_nlink}")
    print(f"  Flags:             0x{ib_flags:08X}")
    print(f"  Size:              {ib_size:,} bytes")
    print(f"  SizeCompressed:    {ib_size_compressed:,} bytes")
    print(f"  Blocks:            {ib_blocks}")
    print(f"  DB[0]:             {ib_db_ptrs[0]} (should be 1)")
    print(f"  DB[1]:             {ib_db_ptrs[1]} (should be -1)")

    # Check seed field (at 0x370)
    if len(data) >= 0x380:
        (seed_marker,) = struct.unpack_from("<I", data, 0x368)
        seed_data = data[0x370:0x380]
        print("\n[SEED FIELD - Offset 0x368-0x37F]")
        print(f"  Marker at 0x368:   0x{seed_marker:08X}")
        print(f"  Seed (16 bytes):   {seed_data.hex()}")

    return True


if __name__ == "__main__":
    filepath = sys.argv[1] if len(sys.argv) > 1 else "~/temp/pfs_image.dat"
    analyze_pfs_header(filepath)
