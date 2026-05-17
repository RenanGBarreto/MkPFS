"""Verify fpt_hash and make_fpt_and_collision_blob match legacy/ffpfs.py.

Tests the flat path table hash function and collision blob generation
used for efficient filename lookups in PFS images.
"""

import struct
from pathlib import Path

import mkpfs.consts as c
import mkpfs.pfs as pfs_mod
from mkpfs.pfs import DirNode, FileNode, Inode, fpt_hash, make_fpt_and_collision_blob


def _make_simple_inode(number: int) -> Inode:
    """Create a minimal inode for testing."""
    return Inode(
        number=number,
        mode=c.INODE_MODE_FILE | c.INODE_RX_ONLY,
        nlink=1,
        flags=c.INODE_FLAG_READONLY,
        size=0,
        size_compressed=0,
        blocks=1,
    )


class TestFptHash:
    """Tests for the flat path table hash function."""

    def test_fpt_hash_case_insensitive_known(self) -> None:
        """Hash of '/eboot.bin' case-insensitive must match legacy algorithm."""
        name: str = "/eboot.bin"
        expected: int = 0
        for ch in name:
            expected = (ord(ch.upper()) + 31 * expected) & 0xFFFFFFFF
        assert fpt_hash(name, case_insensitive=True) == expected

    def test_fpt_hash_case_sensitive(self) -> None:
        """Hash of '/eboot.bin' case-sensitive must match legacy algorithm."""
        name: str = "/eboot.bin"
        expected: int = 0
        for ch in name:
            expected = (ord(ch) + 31 * expected) & 0xFFFFFFFF
        assert fpt_hash(name, case_insensitive=False) == expected

    def test_fpt_hash_differs_by_case_when_case_sensitive(self) -> None:
        """Upper and lower case hashes differ when case-sensitive."""
        assert fpt_hash("/ABC", case_insensitive=False) != fpt_hash("/abc", case_insensitive=False)

    def test_fpt_hash_same_by_case_when_case_insensitive(self) -> None:
        """Upper and lower case hashes match when case-insensitive."""
        assert fpt_hash("/ABC", case_insensitive=True) == fpt_hash("/abc", case_insensitive=True)

    def test_fpt_hash_empty_string(self) -> None:
        """Hash of empty string must be 0."""
        assert fpt_hash("", case_insensitive=True) == 0

    def test_fpt_hash_single_char(self) -> None:
        """Hash of single character is the character's ord value."""
        assert fpt_hash("A", case_insensitive=False) == ord("A")
        assert fpt_hash("a", case_insensitive=False) == ord("a")
        assert fpt_hash("A", case_insensitive=True) == ord("A")
        assert fpt_hash("a", case_insensitive=True) == ord("A")  # both uppercase


class TestMakeFptAndCollisionBlob:
    """Tests for FPT and collision blob generation."""

    def test_fpt_no_collision_single_file(self) -> None:
        """Single file produces one FPT entry, no collision blob."""
        root_dir: DirNode = DirNode(rel_dir="", name="uroot", parent_rel_dir=None)
        f: FileNode = FileNode(
            rel_path="eboot.bin",
            abs_path=Path("/fake/eboot.bin"),
            parent_rel_dir="",
            name="eboot.bin",
            raw_size=0,
        )
        f_ino: Inode = _make_simple_inode(3)
        f.inode = f_ino

        inode_by_path: dict[str, Inode] = {"file:eboot.bin": f_ino}
        fpt: bytes
        collision: bytes | None
        has_collision: bool
        fpt, collision, has_collision = make_fpt_and_collision_blob(
            dirs_sorted=[root_dir],
            files_sorted=[f],
            inode_by_path=inode_by_path,
            case_insensitive=True,
        )
        assert not has_collision
        assert collision is None
        # FPT must have exactly one entry: 8 bytes (hash + value)
        assert len(fpt) == 8
        h: int
        val: int
        h, val = struct.unpack_from("<II", fpt, 0)
        assert h == fpt_hash("/eboot.bin", case_insensitive=True)
        # value = inode_number (no dir flag)
        assert val == 3

    def test_fpt_dir_flag_set(self) -> None:
        """Directory entries set bit 29 (0x20000000) in the FPT value."""
        d: DirNode = DirNode(rel_dir="sce_sys", name="sce_sys", parent_rel_dir="")
        d_ino: Inode = Inode(
            number=4,
            mode=c.INODE_MODE_DIR | c.INODE_RX_ONLY,
            nlink=2,
            flags=c.INODE_FLAG_READONLY,
            size=65536,
            size_compressed=65536,
            blocks=1,
        )
        d.inode = d_ino

        inode_by_path: dict[str, Inode] = {"dir:sce_sys": d_ino}
        fpt: bytes
        collision: bytes | None
        fpt, collision, _ = make_fpt_and_collision_blob(
            dirs_sorted=[DirNode(rel_dir="", name="uroot", parent_rel_dir=None), d],
            files_sorted=[],
            inode_by_path=inode_by_path,
            case_insensitive=True,
        )
        assert collision is None
        _h: int
        val: int
        _h, val = struct.unpack_from("<II", fpt, 0)
        # dir entries have 0x20000000 ORed in
        assert val == (4 | 0x20000000)

    def test_fpt_collision_blob_terminator(self) -> None:
        """Collision blob entries end with 0x18 bytes of zero padding."""
        # Force a collision by monkey-patching fpt_hash
        original_fpt_hash = pfs_mod.fpt_hash

        try:
            # Monkeypatch to force all to same hash
            pfs_mod.fpt_hash = lambda name, case_insensitive=True: 0xDEADBEEF
            f1: FileNode = FileNode(
                rel_path="a",
                abs_path=Path("/fake/a"),
                parent_rel_dir="",
                name="a",
                raw_size=0,
            )
            f1.inode = _make_simple_inode(3)
            f2: FileNode = FileNode(
                rel_path="b",
                abs_path=Path("/fake/b"),
                parent_rel_dir="",
                name="b",
                raw_size=0,
            )
            f2.inode = _make_simple_inode(4)
            inode_by_path: dict[str, Inode] = {"file:a": f1.inode, "file:b": f2.inode}
            root: DirNode = DirNode(rel_dir="", name="uroot", parent_rel_dir=None)
            fpt: bytes
            blob: bytes | None
            has_collision: bool
            fpt, blob, has_collision = make_fpt_and_collision_blob(
                dirs_sorted=[root],
                files_sorted=[f1, f2],
                inode_by_path=inode_by_path,
                case_insensitive=True,
            )
            assert has_collision
            assert blob is not None
            # blob ends with 0x18 zero bytes per collision group
            assert blob[-0x18:] == b"\x00" * 0x18
            # FPT entry value must have 0x80000000 set (collision pointer)
            _h: int
            val: int
            _h, val = struct.unpack_from("<II", fpt, 0)
            assert val & 0x80000000 != 0
        finally:
            pfs_mod.fpt_hash = original_fpt_hash

    def test_fpt_no_collision_multiple_files(self) -> None:
        """Multiple files with different hashes produce multiple FPT entries."""
        f1: FileNode = FileNode(
            rel_path="eboot.bin",
            abs_path=Path("/fake/eboot.bin"),
            parent_rel_dir="",
            name="eboot.bin",
            raw_size=0,
        )
        f1.inode = _make_simple_inode(3)
        f2: FileNode = FileNode(
            rel_path="config.json",
            abs_path=Path("/fake/config.json"),
            parent_rel_dir="",
            name="config.json",
            raw_size=0,
        )
        f2.inode = _make_simple_inode(4)
        inode_by_path: dict[str, Inode] = {"file:eboot.bin": f1.inode, "file:config.json": f2.inode}
        root: DirNode = DirNode(rel_dir="", name="uroot", parent_rel_dir=None)
        fpt: bytes
        collision: bytes | None
        has_collision: bool
        fpt, collision, has_collision = make_fpt_and_collision_blob(
            dirs_sorted=[root],
            files_sorted=[f1, f2],
            inode_by_path=inode_by_path,
            case_insensitive=True,
        )
        assert not has_collision
        assert collision is None
        # FPT must have 2 entries: 16 bytes
        assert len(fpt) == 16
