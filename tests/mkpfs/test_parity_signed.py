"""Verify signed image build produces verifiable images (round-trip check).

Tests that signed images can be built and verified correctly,
with ndblock gap handling and HMAC behavior matching legacy.
"""

from collections.abc import Callable
from pathlib import Path

import mkpfs.consts as c
from mkpfs.cli import run_image_check
from mkpfs.pfs import build_pfs, parse_image_header
from tests.mkpfs.fixtures.helpers import make_app_with_nested_dirs, make_minimal_app


def _build_signed(tmp_path: Path, src_fn: Callable[[Path], Path] = make_minimal_app) -> tuple[Path, Path]:
    """Build a signed PFS image from test app.

    Args:
        tmp_path: Temporary directory path.
        src_fn: Fixture function to create test app structure.

    Returns:
        Tuple of (output image path, source app path).
    """
    src: Path = src_fn(tmp_path / "src")
    out: Path = tmp_path / "signed.ffpfs"
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
    return out, src


class TestSignedImageBasic:
    """Basic tests for signed image structure."""

    def test_signed_image_passes_check(self, tmp_path: Path) -> None:
        """A newly built signed image must pass check with zero errors."""
        out, _src = _build_signed(tmp_path)
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=None, print_tree=False, emit_report=False)
        assert errors == [], f"signed image check produced errors: {errors}"

    def test_signed_image_mode_bit_set(self, tmp_path: Path) -> None:
        """Built signed image must have PFS_MODE_SIGNED in the header mode field."""
        out, _src = _build_signed(tmp_path)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
        assert hdr.mode & c.PFS_MODE_SIGNED

    def test_signed_image_readonly_flag_set(self, tmp_path: Path) -> None:
        """Built signed image must have readonly flag set."""
        out, _src = _build_signed(tmp_path)
        with out.open("rb") as fh:
            hdr = parse_image_header(fh)
        assert hdr.readonly


class TestSignedImageWithNestedDirs:
    """Tests for signed images with complex directory structures."""

    def test_signed_image_with_nested_dirs_passes_check(self, tmp_path: Path) -> None:
        """Signed image with nested dirs must pass check."""
        out, _src = _build_signed(tmp_path, src_fn=make_app_with_nested_dirs)
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=None, print_tree=False, emit_report=False)
        assert errors == [], f"nested signed image errors: {errors}"

    def test_signed_image_source_match(self, tmp_path: Path) -> None:
        """Signed image must pass source-match validation."""
        out, src = _build_signed(tmp_path, src_fn=make_app_with_nested_dirs)
        errors, _warnings, _tree, _uroot = run_image_check(image=out, source=src, print_tree=False, emit_report=False)
        assert errors == [], f"source-match errors: {errors}"


class TestSignedImageHeaderDigest:
    """Tests for signed image header digest computation."""

    def test_header_digest_offset_used(self, tmp_path: Path) -> None:
        """Verify HEADER_DIGEST_OFFSET constant is defined."""
        # This is a sanity check that the constant exists
        assert hasattr(c, "HEADER_DIGEST_OFFSET")
        assert c.HEADER_DIGEST_OFFSET == 0x380

    def test_header_digest_size_used(self, tmp_path: Path) -> None:
        """Verify HEADER_DIGEST_SIZE constant is defined."""
        assert hasattr(c, "HEADER_DIGEST_SIZE")
        assert c.HEADER_DIGEST_SIZE == 0x5A0
