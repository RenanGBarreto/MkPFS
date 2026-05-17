"""Verify build_pfs inode flags match legacy/ffpfs.py.

Tests that signed images have the correct INODE_FLAG_SIGNED_EXTRA flags
set on superroot, uroot, and file inodes.
"""

from pathlib import Path

import mkpfs.consts as c
from mkpfs.pfs import build_pfs, parse_image_header, parse_image_inodes
from tests.mkpfs.fixtures.helpers import make_app_with_nested_dirs, make_minimal_app


def _build(tmp_path: Path, signed: bool = False) -> Path:
    """Build a PFS image from minimal test app.

    Args:
        tmp_path: Temporary directory path.
        signed: Whether to build a signed image.

    Returns:
        Path to the output image file.
    """
    src: Path = make_minimal_app(tmp_path / "src")
    out: Path = tmp_path / "out.ffpfs"
    build_pfs(
        source_root=src,
        output_path=out,
        block_size=65536,
        pfs_version=c.PFS_VERSION_PS4,
        inode_bits=32,
        case_insensitive=True,
        signed=signed,
        compress=False,
        threshold_gain=20,
        cpu_count=1,
        zlib_level=9,
        dry_run=False,
        verbose=False,
    )
    return out


class TestUnsignedInodeFlags:
    """Tests for inode flags in unsigned images."""

    def test_unsigned_superroot_flags(self, tmp_path: Path) -> None:
        """Superroot in unsigned image must have INTERNAL and READONLY."""
        out: Path = _build(tmp_path, signed=False)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
            inodes = parse_image_inodes(fh, hdr)
        # inode 0 is superroot
        sr = inodes[0]
        assert sr.flags & c.INODE_FLAG_INTERNAL
        assert sr.flags & c.INODE_FLAG_READONLY
        assert not (sr.flags & c.INODE_FLAG_SIGNED_EXTRA)

    def test_unsigned_uroot_flags(self, tmp_path: Path) -> None:
        """Uroot in unsigned image must have READONLY, not SIGNED_EXTRA."""
        out: Path = _build(tmp_path, signed=False)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
            inodes = parse_image_inodes(fh, hdr)
        # uroot is inode 2 (no collision in minimal app)
        uroot = inodes[2]
        assert uroot.flags & c.INODE_FLAG_READONLY
        assert not (uroot.flags & c.INODE_FLAG_SIGNED_EXTRA)

    def test_file_inode_flags_unsigned(self, tmp_path: Path) -> None:
        """All file inodes in unsigned image must have READONLY, not SIGNED_EXTRA."""
        out: Path = _build(tmp_path, signed=False)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
            inodes = parse_image_inodes(fh, hdr)
        # All file inodes must have READONLY set and no SIGNED_EXTRA
        file_inodes = [i for i in inodes if i.mode & c.INODE_MODE_FILE]
        for fi in file_inodes:
            assert fi.flags & c.INODE_FLAG_READONLY, f"inode {fi.number} missing READONLY"
            assert not (fi.flags & c.INODE_FLAG_SIGNED_EXTRA), f"inode {fi.number} has SIGNED_EXTRA in unsigned image"


class TestSignedInodeFlags:
    """Tests for inode flags in signed images."""

    def test_signed_superroot_flags(self, tmp_path: Path) -> None:
        """Superroot in signed image must have INTERNAL and SIGNED_EXTRA, not READONLY."""
        out: Path = _build(tmp_path, signed=True)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
            inodes = parse_image_inodes(fh, hdr)
        sr = inodes[0]
        assert sr.flags & c.INODE_FLAG_INTERNAL
        assert not (sr.flags & c.INODE_FLAG_READONLY)  # cleared for signed
        assert sr.flags & c.INODE_FLAG_SIGNED_EXTRA

    def test_signed_uroot_flags(self, tmp_path: Path) -> None:
        """Uroot in signed image must have SIGNED_EXTRA, not READONLY."""
        out: Path = _build(tmp_path, signed=True)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
            inodes = parse_image_inodes(fh, hdr)
        uroot = inodes[2]
        assert not (uroot.flags & c.INODE_FLAG_READONLY)
        assert uroot.flags & c.INODE_FLAG_SIGNED_EXTRA

    def test_file_inode_flags_signed(self, tmp_path: Path) -> None:
        """All file inodes in signed image must have SIGNED_EXTRA and READONLY."""
        out: Path = _build(tmp_path, signed=True)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
            inodes = parse_image_inodes(fh, hdr)
        file_inodes = [i for i in inodes if i.mode & c.INODE_MODE_FILE and not (i.flags & c.INODE_FLAG_INTERNAL)]
        for fi in file_inodes:
            assert fi.flags & c.INODE_FLAG_READONLY, f"inode {fi.number} missing READONLY"
            assert fi.flags & c.INODE_FLAG_SIGNED_EXTRA, f"inode {fi.number} missing SIGNED_EXTRA"

    def test_directory_inode_flags_signed(self, tmp_path: Path) -> None:
        """All directory inodes in signed image must have SIGNED_EXTRA."""
        out: Path = _build(tmp_path, signed=True)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
            inodes = parse_image_inodes(fh, hdr)
        # Non-superroot directories should have SIGNED_EXTRA
        dir_inodes = [
            i
            for i in inodes
            if (i.mode & c.INODE_MODE_DIR) and not (i.flags & c.INODE_FLAG_INTERNAL) and i.number != 0
        ]
        for di in dir_inodes:
            assert di.flags & c.INODE_FLAG_SIGNED_EXTRA, f"dir inode {di.number} missing SIGNED_EXTRA"


class TestSignedImageRoundTrip:
    """Round-trip tests for signed images."""

    def test_signed_image_passes_check(self, tmp_path: Path) -> None:
        """A newly built signed image must pass check with zero errors."""
        from mkpfs.cli import run_image_check

        out: Path = _build(tmp_path, signed=True)
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=None, print_tree=False, emit_report=False)
        assert errors == [], f"signed image check produced errors: {errors}"

    def test_signed_image_mode_bit_set(self, tmp_path: Path) -> None:
        """Built signed image must have PFS_MODE_SIGNED in the header mode field."""
        out: Path = _build(tmp_path, signed=True)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
        assert hdr.mode & c.PFS_MODE_SIGNED

    def test_signed_image_with_nested_dirs_passes_check(self, tmp_path: Path) -> None:
        """Signed image with nested dirs must pass check."""
        from mkpfs.cli import run_image_check

        src: Path = make_app_with_nested_dirs(tmp_path / "src")
        out: Path = tmp_path / "out.ffpfs"
        build_pfs(
            source_root=src,
            output_path=out,
            block_size=65536,
            pfs_version=c.PFS_VERSION_PS4,
            inode_bits=32,
            case_insensitive=True,
            signed=True,
            compress=False,
            threshold_gain=20,
            cpu_count=1,
            zlib_level=9,
            dry_run=False,
            verbose=False,
        )
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=None, print_tree=False, emit_report=False)
        assert errors == [], f"nested signed image errors: {errors}"

    def test_signed_image_source_match(self, tmp_path: Path) -> None:
        """Signed image must pass source-match validation."""
        from mkpfs.cli import run_image_check

        src: Path = make_app_with_nested_dirs(tmp_path / "src")
        out: Path = tmp_path / "out.ffpfs"
        build_pfs(
            source_root=src,
            output_path=out,
            block_size=65536,
            pfs_version=c.PFS_VERSION_PS4,
            inode_bits=32,
            case_insensitive=True,
            signed=True,
            compress=False,
            threshold_gain=20,
            cpu_count=1,
            zlib_level=9,
            dry_run=False,
            verbose=False,
        )
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=src, print_tree=False, emit_report=False)
        assert errors == [], f"source-match errors: {errors}"
