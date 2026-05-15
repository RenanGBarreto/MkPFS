from pathlib import Path
from types import SimpleNamespace

import pytest

from mkpfs import logging as mkp_logging
from mkpfs.cli import (
    cli_mkpfs_analyze_run,
    cli_mkpfs_check_run,
    cli_mkpfs_create_run,
    cli_mkpfs_extract_run,
    cli_mkpfs_info_run,
    cli_mkpfs_ls_run,
    parse_args,
    print_build_parameters,
    print_summary,
)
from mkpfs.pfs import (
    BuildStats,
    ParsedDirent,
    PFSExtractionResult,
    PFSImageInfo,
    PFSImageInspection,
)


def test_logging_ascii_icons_env_disabled(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    # Force ASCII fallback via environment
    monkeypatch.setenv("MKPFS_NO_UTF8", "1")
    mkp_logging.info("hello", icon_name="info")
    mkp_logging.error("bad", icon_name="error")
    mkp_logging.log(message={"a": 1}, level=0)
    captured = capsys.readouterr()
    # info should go to stdout with ascii prefix ("i" or similar)
    assert "hello" in captured.out
    # error should go to stderr
    assert "bad" in captured.err
    # log should stringify non-string objects
    assert "{'a': 1}" in captured.out


def test_print_build_parameters_and_summary(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    src = tmp_path / "src"
    out = tmp_path / "out.ffpfs"
    # Call print_build_parameters
    print_build_parameters(
        source_path=src,
        output_path=out,
        block_size=65536,
        pfs_version=0,
        inode_bits=32,
        case_insensitive=False,
        signed=False,
        compress=True,
        threshold_gain=20,
        cpu_count=0,
        zlib_level=9,
        dry_run=True,
    )
    out_capture = capsys.readouterr()
    assert "PFS Image Builder - Parameters" in out_capture.out

    # BuildStats for summary
    stats = BuildStats(input_path=src, output_path=out)
    stats.total_files = 2
    stats.uncompressed_total_size = 1024
    stats.stored_total_size = 512
    stats.compression_enabled = True
    stats.compressed_files = 1
    stats.uncompressed_files = 1
    stats.all_compressed_total_size = 400
    stats.block_alignment_waste = 128
    stats.elapsed_seconds = 1.5
    print_summary(stats)
    captured = capsys.readouterr()
    assert "Build Summary" in captured.out
    assert "Total files" in captured.out or "Total files:" in captured.out


def test_parse_args_basic() -> None:
    args = parse_args(["--path", "p", "--output", "o", "--block-size", "auto"])
    assert args.path == "p"
    assert args.output == "o"


def test_create_verify_flows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    src = tmp_path / "s"
    src.mkdir()
    (src / "sce_sys").mkdir()
    (src / "sce_sys" / "param.json").write_text('{"titleId":"T"}')
    out = tmp_path / "out.ffpfs"

    # monkeypatch build_pfs to return stats
    monkeypatch.setattr("mkpfs.cli.build_pfs", lambda **kwargs: BuildStats(input_path=src, output_path=out))
    # prompt_overwrite should be True
    monkeypatch.setattr("mkpfs.cli.prompt_overwrite", lambda p: True)

    # case: verify returns no errors
    monkeypatch.setattr("mkpfs.cli.run_image_check", lambda *a, **k: ([], [], {}, -1))
    args = SimpleNamespace(
        path=str(src),
        output=str(out),
        no_compress=False,
        threshold_gain=20,
        block_size="auto",
        version="PS4",
        inode_bits=32,
        case_sensitive=False,
        case_insensitive=True,
        cpu_count=0,
        compression_level=9,
        signed=False,
        verbose=False,
        dry_run=False,
        verify=True,
    )
    rc = cli_mkpfs_create_run(args)
    assert rc == 0

    # case: verify returns errors
    monkeypatch.setattr("mkpfs.cli.run_image_check", lambda *a, **k: (["e"], [], {}, -1))
    rc2 = cli_mkpfs_create_run(args)
    assert rc2 == 1


def test_check_valid_crc_and_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    # valid hex crc and valid manifest digest length
    monkeypatch.setattr("mkpfs.cli.run_image_check", lambda *a, **k: ([], [], {}, -1))
    args = SimpleNamespace(
        image="i", expected_crc32="0x7F528D1F", expected_manifest_sha256="" * 64, print_tree=False, source=None
    )
    # expected_manifest_sha256 will be checked for length, so provide 64 hex chars.
    args.expected_manifest_sha256 = "a" * 64
    rc = cli_mkpfs_check_run(args)
    assert rc == 0


def test_analyze_print_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    inspection = PFSImageInspection(image=Path("img"))
    inspection.header = SimpleNamespace(version=0, block_size=65536)
    inspection.warnings = []
    inspection.errors = []
    inspection.dirents_by_inode = {0: [ParsedDirent(inode_number=1, type_code=1, name="file")]}  # type_code arbitrary
    inspection.uroot_inode = 0
    monkeypatch.setattr("mkpfs.cli.inspect_pfs_image", lambda **k: inspection)

    args = SimpleNamespace(
        image="img", source=None, expected_crc32=None, expected_manifest_sha256=None, print_tree=True
    )
    rc = cli_mkpfs_analyze_run(args)
    assert rc == 0


def test_info_and_ls_and_extract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # info with warnings/errors
    info = PFSImageInfo(image=Path("img"))
    info.warnings = ["w"]
    info.errors = ["e"]
    monkeypatch.setattr("mkpfs.cli.read_pfs_info", lambda image: info)
    rc = cli_mkpfs_info_run(SimpleNamespace(image="img"))
    assert rc == 1

    # ls printing tree
    monkeypatch.setattr(
        "mkpfs.cli.run_image_check",
        lambda *a, **k: ([], [], {0: [ParsedDirent(inode_number=1, type_code=1, name="file")]}, 0),
    )
    rc2 = cli_mkpfs_ls_run(SimpleNamespace(image="img"))
    assert rc2 == 0

    # extract success
    res = PFSExtractionResult(
        image=Path("img"), output_path=tmp_path / "out", files_written=1, directories_created=1, bytes_written=10
    )
    monkeypatch.setattr("mkpfs.cli.extract_pfs_image", lambda image, output_path, progress=None: res)
    args = SimpleNamespace(image="img", output=str(tmp_path / "out"), overwrite=True)
    rc3 = cli_mkpfs_extract_run(args)
    assert rc3 == 0
