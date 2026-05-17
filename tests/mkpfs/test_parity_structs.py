"""Verify Dirent and Inode serialization matches legacy/ffpfs.py byte-for-byte.

Tests the on-disk layout of directory entries (dirent) and inode structures
used in both signed (S32) and unsigned (D32) inode formats.
"""

import io
import struct

import mkpfs.consts as c
from mkpfs.pfs import Dirent, Inode, parse_image_header


def test_dirent_to_bytes_known_vector() -> None:
    """Encode a file dirent for inode 5, name "eboot.bin" (9 chars)."""
    d: Dirent = Dirent(inode_number=5, type_code=c.DIRENT_TYPE_FILE, name="eboot.bin")
    assert d.name_length == 9
    assert d.ent_size == 32  # (9 + 17 = 26) -> round up to next 8 -> 32
    b: bytes = d.to_bytes()
    assert len(b) == 32
    ino_num, type_code, name_len, ent_sz = struct.unpack_from("<Iiii", b, 0)
    assert ino_num == 5
    assert type_code == c.DIRENT_TYPE_FILE
    assert name_len == 9
    assert ent_sz == 32
    assert b[16:25] == b"eboot.bin"
    assert b[25:32] == b"\x00" * 7


def test_dirent_dot() -> None:
    """Directory entry for "." (current directory)."""
    d: Dirent = Dirent(inode_number=2, type_code=c.DIRENT_TYPE_DOT, name=".")
    # name_length=1, ent_size = (1 + 17 = 18) -> round up to 24
    assert d.ent_size == 24
    b: bytes = d.to_bytes()
    assert len(b) == 24


def test_dirent_dotdot() -> None:
    """Directory entry for ".." (parent directory)."""
    d: Dirent = Dirent(inode_number=0, type_code=c.DIRENT_TYPE_DOTDOT, name="..")
    # name_length=2, ent_size = (2 + 17 = 19) -> round up to 24
    assert d.ent_size == 24
    b: bytes = d.to_bytes()
    assert len(b) == 24


def test_dirent_directory() -> None:
    """Directory entry for a subdirectory."""
    d: Dirent = Dirent(inode_number=10, type_code=c.DIRENT_TYPE_DIRECTORY, name="sce_sys")
    # name_length=7, ent_size = (7 + 17 = 24) -> already aligned
    assert d.ent_size == 24
    b: bytes = d.to_bytes()
    assert len(b) == 24


def test_inode_d32_size() -> None:
    """D32 inode serialization must produce exactly INODE_D32_SIZE bytes."""
    ino: Inode = Inode(
        number=1,
        mode=0x81A9,
        nlink=1,
        flags=c.INODE_FLAG_READONLY,
        size=1024,
        size_compressed=1024,
        blocks=1,
    )
    b: bytes = ino.to_bytes()
    assert len(b) == c.INODE_D32_SIZE  # 0xA8 = 168


def test_inode_d32_field_layout() -> None:
    """Verify D32 inode field positions match legacy parse_image_inode offsets.

    Legacy offsets:
    - mode at 0x00
    - nlink at 0x02
    - flags at 0x04
    - size at 0x08
    - size_compressed at 0x10
    - blocks at 0x60
    - db[0..11] at 0x64
    - ib[0..4] at 0x94
    """
    ino: Inode = Inode(
        number=7,
        mode=0x8000,
        nlink=3,
        flags=0x10,
        size=512,
        size_compressed=512,
        blocks=1,
    )
    ino.db[0] = 42
    ino.ib[0] = 99
    b: bytes = ino.to_bytes()
    assert struct.unpack_from("<H", b, 0x00)[0] == 0x8000  # mode
    assert struct.unpack_from("<H", b, 0x02)[0] == 3  # nlink
    assert struct.unpack_from("<I", b, 0x04)[0] == 0x10  # flags
    assert struct.unpack_from("<q", b, 0x08)[0] == 512  # size
    assert struct.unpack_from("<q", b, 0x10)[0] == 512  # size_compressed
    assert struct.unpack_from("<I", b, 0x60)[0] == 1  # blocks
    assert struct.unpack_from("<i", b, 0x64)[0] == 42  # db[0]
    assert struct.unpack_from("<i", b, 0x64 + 12 * 4)[0] == 99  # ib[0] at 0x94


def test_inode_s32_size() -> None:
    """S32 signed inode serialization must produce exactly INODE_S32_SIZE bytes."""
    ino: Inode = Inode(
        number=1,
        mode=0x81A9,
        nlink=1,
        flags=0,
        size=0,
        size_compressed=0,
        blocks=1,
    )
    b: bytes = ino.to_bytes_signed32()
    assert len(b) == c.INODE_S32_SIZE  # 0x2C8 = 712


def test_inode_s32_db_layout() -> None:
    """In S32 layout: each db entry is 32-byte sig + 4-byte block pointer.

    db[0] starts at 0x64: sig at 0x64..0x83, block at 0x84.
    """
    ino: Inode = Inode(
        number=1,
        mode=0x8000,
        nlink=1,
        flags=0,
        size=0,
        size_compressed=0,
        blocks=1,
    )
    ino.db[0] = 55
    b: bytes = ino.to_bytes_signed32()
    # sig at 0x64 (32 bytes of zeros)
    assert b[0x64 : 0x64 + 32] == b"\x00" * 32
    # block pointer at 0x64 + 32 = 0x84
    assert struct.unpack_from("<i", b, 0x84)[0] == 55


def test_inode_s32_ib_layout() -> None:
    """In S32 layout: indirect blocks follow direct blocks."""
    ino: Inode = Inode(
        number=1,
        mode=0x8000,
        nlink=1,
        flags=0,
        size=0,
        size_compressed=0,
        blocks=1,
    )
    # db takes up 12 entries * 36 bytes (sig + block) = 432 bytes
    # ib[0] starts at 0x64 + 432 = 0x1E0
    ino.ib[0] = 77
    b: bytes = ino.to_bytes_signed32()
    ib_offset: int = 0x64 + 12 * c.SIG_ENTRY_SIZE
    assert struct.unpack_from("<i", b, ib_offset + c.SIG_SIZE)[0] == 77


def test_parse_image_header_field_offsets() -> None:
    """Build a minimal 0x400-byte header blob with known values.

    Verify parse_image_header reads all fields from correct offsets
    matching legacy/ffpfs.py:parse_image_header.
    """
    hdr: bytearray = bytearray(0x400)
    struct.pack_into("<qq", hdr, 0x00, 1, 20130315)  # version=1, magic
    struct.pack_into("<B", hdr, 0x1A, 1)  # readonly=1
    struct.pack_into("<H", hdr, 0x1C, 0x8)  # mode=case-insensitive
    struct.pack_into("<I", hdr, 0x20, 65536)  # block_size
    struct.pack_into("<q", hdr, 0x28, 100)  # nblock
    struct.pack_into("<q", hdr, 0x30, 50)  # dinode_count
    struct.pack_into("<q", hdr, 0x38, 200)  # ndblock
    struct.pack_into("<q", hdr, 0x40, 2)  # dinode_block_count
    seed_val: bytes = bytes(range(16))
    hdr[0x370:0x380] = seed_val

    fh: io.BytesIO = io.BytesIO(bytes(hdr))
    h = parse_image_header(fh)
    assert h.version == 1
    assert h.magic == 20130315
    assert h.readonly == 1
    assert h.mode == 0x8
    assert h.block_size == 65536
    assert h.nblock == 100
    assert h.dinode_count == 50
    assert h.ndblock == 200
    assert h.dinode_block_count == 2
    assert h.seed == seed_val
