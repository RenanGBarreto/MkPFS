from pathlib import Path
from types import SimpleNamespace

import pytest

from mkpfs.cli import (
    cli_mkpfs_analyze_run,
    cli_mkpfs_check_run,
    cli_mkpfs_extract_run,
    cli_mkpfs_info_run,
    cli_mkpfs_ls_run,
    prompt_overwrite,
)


def test_prompt_overwrite_no(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    file_path = tmp_path / "out.img"
    file_path.write_text("x")
    # Simulate user entering 'n'
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert prompt_overwrite(file_path) is False


def test_prompt_overwrite_yes_cleans_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    file_path = tmp_path / "out.img"
    file_path.write_text("x")
    tmp_file = Path(str(file_path) + ".tmp")
    tmp_file.write_text("partial")
    # Simulate user entering 'y'
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    assert prompt_overwrite(file_path) is True
    # tmp file should be removed
    assert not tmp_file.exists()


def test_cli_extract_existing_no_overwrite(tmp_path: Path) -> None:
    outdir = tmp_path / "outdir"
    outdir.mkdir()
    args = SimpleNamespace(image="does-not-exist.img", output=str(outdir), overwrite=False)
    rc = cli_mkpfs_extract_run(args)
    assert rc == 2


def test_cli_check_bad_crc() -> None:
    args = SimpleNamespace(
        image="img", expected_crc32="0xZZ", expected_manifest_sha256=None, print_tree=False, source=None
    )
    rc = cli_mkpfs_check_run(args)
    assert rc == 2


def test_cli_analyze_bad_manifest() -> None:
    args = SimpleNamespace(
        image="img", source=None, expected_crc32=None, expected_manifest_sha256="deadbeef", print_tree=False
    )
    rc = cli_mkpfs_analyze_run(args)
    assert rc == 2


def test_cli_ls_nonexistent_image() -> None:
    args = SimpleNamespace(image="no-such-image.img")
    rc = cli_mkpfs_ls_run(args)
    assert rc == 1


def test_cli_info_nonexistent_image() -> None:
    args = SimpleNamespace(image="no-such-image.img")
    rc = cli_mkpfs_info_run(args)
    assert rc == 1
