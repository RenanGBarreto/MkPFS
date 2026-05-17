"""Side-by-side runtime parity: legacy/ffpfs.py vs mkpfs.pfs.build_pfs.

Runs both implementations on identical inputs and compares output images
and check/ls output byte-by-byte / line-by-line.

Legacy is invoked via subprocess in read-only fashion.
Temporary artifacts land in tmp/parity/ (not committed).
"""

import subprocess
import sys
from pathlib import Path

import pytest

import mkpfs.consts as c
from mkpfs.cli import run_image_check
from mkpfs.pfs import build_pfs
from tests.mkpfs.fixtures.helpers import make_app_with_nested_dirs, make_minimal_app

LEGACY_SCRIPT: Path = Path(__file__).resolve().parents[2] / "legacy" / "ffpfs.py"


def _run_legacy_build(src: Path, out: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run legacy ffpfs.py create command with specified arguments.

    Args:
        src: Source directory containing app to package.
        out: Output image path.
        extra_args: Additional command-line arguments (e.g., --signed).

    Returns:
        CompletedProcess with return code, stdout, and stderr.
    """
    cmd: list[str] = [
        sys.executable,
        str(LEGACY_SCRIPT),
        "create",
        "--path",
        str(src),
        "--output",
        str(out),
        "--no-compress",
        "--block-size",
        "65536",
        "--version",
        "PS4",
        "--inode-bits",
        "32",
        "--case-insensitive",
    ] + (extra_args or [])
    return subprocess.run(cmd, capture_output=True, text=True)


def _build_new(src: Path, out: Path, signed: bool = False) -> None:
    """Build image using new mkpfs implementation.

    Args:
        src: Source directory containing app to package.
        out: Output image path.
        signed: Whether to create a signed image.
    """
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


@pytest.fixture(autouse=True)
def parity_tmp(tmp_path: Path) -> Path:
    """Ensure tmp/parity directory exists for temporary test artifacts.

    Args:
        tmp_path: pytest's temporary directory fixture.

    Returns:
        Path to parity directory.
    """
    parity: Path = Path("tmp/parity")
    parity.mkdir(parents=True, exist_ok=True)
    return parity


def test_unsigned_image_byte_identical(tmp_path: Path) -> None:
    """Unsigned image bytes must be identical between legacy and new build.

    Args:
        tmp_path: pytest temporary directory.
    """
    src: Path = make_minimal_app(tmp_path / "src")

    legacy_out: Path = tmp_path / "legacy.ffpfs"
    result: subprocess.CompletedProcess[str] = _run_legacy_build(src, legacy_out)
    assert result.returncode == 0, f"Legacy build failed: {result.stderr}"

    new_out: Path = tmp_path / "new.ffpfs"
    _build_new(src, new_out)

    assert legacy_out.read_bytes() == new_out.read_bytes(), (
        "Unsigned image bytes differ between legacy and new implementation"
    )


def test_unsigned_check_agrees(tmp_path: Path) -> None:
    """New check command accepts legacy-built unsigned image.

    Args:
        tmp_path: pytest temporary directory.
    """
    src: Path = make_minimal_app(tmp_path / "src")

    legacy_out: Path = tmp_path / "legacy.ffpfs"
    result: subprocess.CompletedProcess[str] = _run_legacy_build(src, legacy_out)
    assert result.returncode == 0

    errors, _warnings, _tree, _uroot = run_image_check(
        image=legacy_out, source=None, print_tree=False, emit_report=False
    )
    assert errors == [], f"New check found errors in legacy-built image: {errors}"


def test_legacy_check_accepts_new_image(tmp_path: Path) -> None:
    """Legacy check command accepts new-built unsigned image.

    Args:
        tmp_path: pytest temporary directory.
    """
    src: Path = make_minimal_app(tmp_path / "src")
    new_out: Path = tmp_path / "new.ffpfs"
    _build_new(src, new_out)

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, str(LEGACY_SCRIPT), "check", "--image", str(new_out)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Legacy check rejected new image: {result.stdout}\n{result.stderr}"


def test_nested_dirs_unsigned_byte_identical(tmp_path: Path) -> None:
    """Nested directory unsigned image bytes identical between implementations.

    Args:
        tmp_path: pytest temporary directory.
    """
    src: Path = make_app_with_nested_dirs(tmp_path / "src")

    legacy_out: Path = tmp_path / "legacy.ffpfs"
    result: subprocess.CompletedProcess[str] = _run_legacy_build(src, legacy_out)
    assert result.returncode == 0, f"Legacy build failed: {result.stderr}"

    new_out: Path = tmp_path / "new.ffpfs"
    _build_new(src, new_out)

    assert legacy_out.read_bytes() == new_out.read_bytes(), "Nested-dir unsigned image bytes differ"


def test_signed_image_byte_identical(tmp_path: Path) -> None:
    """Signed image bytes must be identical between legacy and new build.

    Args:
        tmp_path: pytest temporary directory.
    """
    src: Path = make_minimal_app(tmp_path / "src")

    legacy_out: Path = tmp_path / "legacy_signed.ffpfs"
    result: subprocess.CompletedProcess[str] = _run_legacy_build(src, legacy_out, extra_args=["--signed"])
    assert result.returncode == 0, f"Legacy signed build failed: {result.stderr}"

    new_out: Path = tmp_path / "new_signed.ffpfs"
    _build_new(src, new_out, signed=True)

    assert legacy_out.read_bytes() == new_out.read_bytes(), (
        "Signed image bytes differ between legacy and new implementation"
    )


def test_signed_legacy_check_accepts_new_signed(tmp_path: Path) -> None:
    """Legacy check accepts new-built signed image.

    Args:
        tmp_path: pytest temporary directory.
    """
    src: Path = make_minimal_app(tmp_path / "src")
    new_out: Path = tmp_path / "new_signed.ffpfs"
    _build_new(src, new_out, signed=True)

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, str(LEGACY_SCRIPT), "check", "--image", str(new_out)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Legacy check rejected new signed image:\n{result.stdout}\n{result.stderr}"


def test_nested_dirs_signed_byte_identical(tmp_path: Path) -> None:
    """Nested directory signed image bytes identical between implementations.

    Args:
        tmp_path: pytest temporary directory.
    """
    src: Path = make_app_with_nested_dirs(tmp_path / "src")

    legacy_out: Path = tmp_path / "legacy_signed.ffpfs"
    result: subprocess.CompletedProcess[str] = _run_legacy_build(src, legacy_out, extra_args=["--signed"])
    assert result.returncode == 0, f"Legacy signed build failed: {result.stderr}"

    new_out: Path = tmp_path / "new_signed.ffpfs"
    _build_new(src, new_out, signed=True)

    assert legacy_out.read_bytes() == new_out.read_bytes(), "Nested-dir signed image bytes differ"
