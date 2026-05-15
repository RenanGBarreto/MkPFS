from pathlib import Path
from types import SimpleNamespace

import pytest

import mkpfs.cli as cli_mod
from mkpfs.pfs import PFSExtractionResult, PFSImageInfo, PFSImageInspection


def test_check_run_no_errors() -> None:
    # Patch run_image_check to return no errors
    from pytest import MonkeyPatch

    mp = MonkeyPatch()
    mp.setattr(
        cli_mod,
        "run_image_check",
        lambda image, source, print_tree, expected_crc32=None, expected_manifest_sha256=None: ([], [], {}, -1),
    )
    args = SimpleNamespace(
        image="img", expected_crc32=None, expected_manifest_sha256=None, print_tree=False, source=None
    )
    rc = cli_mod.cli_mkpfs_check_run(args)
    mp.undo()
    assert rc == 0


def test_check_run_with_errors() -> None:
    from pytest import MonkeyPatch

    mp = MonkeyPatch()
    mp.setattr(
        cli_mod,
        "run_image_check",
        lambda image, source, print_tree, expected_crc32=None, expected_manifest_sha256=None: (
            ["err"],
            ["warn"],
            {},
            -1,
        ),
    )
    args = SimpleNamespace(
        image="img", expected_crc32=None, expected_manifest_sha256=None, print_tree=False, source=None
    )
    rc = cli_mod.cli_mkpfs_check_run(args)
    mp.undo()
    assert rc == 1


def test_analyze_run_no_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    inspection = PFSImageInspection(image=Path("img"))
    monkeypatch.setattr(cli_mod, "inspect_pfs_image", lambda **kwargs: inspection)
    args = SimpleNamespace(
        image="img", source=None, expected_crc32=None, expected_manifest_sha256=None, print_tree=False
    )
    rc = cli_mod.cli_mkpfs_analyze_run(args)
    assert rc == 0


def test_analyze_run_with_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    inspection = PFSImageInspection(image=Path("img"))
    inspection.errors.append("bad")
    monkeypatch.setattr(cli_mod, "inspect_pfs_image", lambda **kwargs: inspection)
    args = SimpleNamespace(
        image="img", source=None, expected_crc32=None, expected_manifest_sha256=None, print_tree=False
    )
    rc = cli_mod.cli_mkpfs_analyze_run(args)
    assert rc == 1


def test_info_run_no_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    info = PFSImageInfo(image=Path("img"))
    monkeypatch.setattr(cli_mod, "read_pfs_info", lambda image: info)
    args = SimpleNamespace(image="img")
    rc = cli_mod.cli_mkpfs_info_run(args)
    assert rc == 0


def test_ls_run_success() -> None:
    from pytest import MonkeyPatch

    mp = MonkeyPatch()
    mp.setattr(cli_mod, "run_image_check", lambda image, source, print_tree, emit_report=False: ([], [], {}, -1))
    args = SimpleNamespace(image="img")
    rc = cli_mod.cli_mkpfs_ls_run(args)
    mp.undo()
    assert rc == 0


def test_extract_run_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    res = PFSExtractionResult(
        image=Path("img"), output_path=tmp_path / "out", files_written=1, directories_created=1, bytes_written=10
    )
    monkeypatch.setattr(cli_mod, "extract_pfs_image", lambda image, output_path, progress=None: res)
    args = SimpleNamespace(image="img", output=str(tmp_path / "out"), overwrite=True)
    rc = cli_mod.cli_mkpfs_extract_run(args)
    assert rc == 0
