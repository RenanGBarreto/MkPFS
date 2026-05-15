from pathlib import Path
from types import SimpleNamespace

import pytest

import mkpfs.cli as cli_mod
from mkpfs import logging as mkp_logging
from mkpfs.pfs import BuildError, BuildStats, PFSExtractionResult, PFSImageInfo, PFSImageInspection


def test_prompt_overwrite_when_output_missing(tmp_path: Path) -> None:
    output_path: Path = tmp_path / "missing.ffpfs"
    assert cli_mod.prompt_overwrite(output_path=output_path) is True


def test_prompt_overwrite_invalid_then_yes_with_unlink_oserror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_path: Path = tmp_path / "existing.ffpfs"
    output_path.write_text("x")
    tmp_partial_path: Path = Path(str(output_path) + ".tmp")
    tmp_partial_path.write_text("partial")

    answers: list[str] = ["maybe", "yes"]

    def fake_input(_prompt: str = "") -> str:
        return answers.pop(0)

    def fake_unlink(self: Path) -> None:
        raise OSError("unlink blocked")

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(Path, "unlink", fake_unlink)
    assert cli_mod.prompt_overwrite(output_path=output_path) is True


def test_create_args_to_legacy_argv_all_flags() -> None:
    args = SimpleNamespace(
        path="src",
        output="out.ffpfs",
        no_compress=True,
        threshold_gain=12,
        block_size="65536",
        version="PS5",
        inode_bits=64,
        case_sensitive=True,
        case_insensitive=False,
        cpu_count=4,
        compression_level=3,
        signed=True,
        verbose=True,
        dry_run=True,
    )
    argv: list[str] = cli_mod.create_args_to_legacy_argv(args=args)
    assert "--no-compress" in argv
    assert "--case-sensitive" in argv
    assert "--signed" in argv
    assert "--verbose" in argv
    assert "--dry-run" in argv


def test_check_run_negative_crc_out_of_range() -> None:
    args = SimpleNamespace(
        image="image.ffpfs",
        source=None,
        expected_crc32="-1",
        expected_manifest_sha256=None,
        print_tree=False,
    )
    assert cli_mod.cli_mkpfs_check_run(args=args) == 2


def test_run_image_check_full_report_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_path: Path = tmp_path / "image.ffpfs"
    image_path.write_bytes(b"x")

    header = SimpleNamespace(
        mode=0,
        version=0,
        magic=123,
        readonly=1,
        block_size=65536,
    )
    inodes = [SimpleNamespace(number=0, is_compressed=False, size=100, size_compressed=90)]

    monkeypatch.setattr(cli_mod, "parse_image_header", lambda _fh: header)
    monkeypatch.setattr(cli_mod, "parse_image_inodes", lambda _fh, _header: inodes)
    monkeypatch.setattr(cli_mod, "validate_inode_layout", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli_mod, "verify_signed_image_signatures", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli_mod, "parse_superroot_and_indexes", lambda *_args, **_kwargs: (0, {1: 2}, {}, {0}))
    monkeypatch.setattr(
        cli_mod, "build_tree_from_uroot", lambda *_args, **_kwargs: ({"file.bin": 0}, {"": 0}, {0: []})
    )
    monkeypatch.setattr(cli_mod, "build_expected_fpt", lambda *_args, **_kwargs: {1: []})
    monkeypatch.setattr(cli_mod, "validate_fpt_maps", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli_mod, "validate_ps5_checklist", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli_mod, "verify_file_payload_hashes", lambda *_args, **_kwargs: (1, 0x1234, "a" * 64))
    monkeypatch.setattr(cli_mod, "validate_source_match", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli_mod, "render_tree", lambda *_args, **_kwargs: ["|- file.bin"])

    errors, warnings, tree, uroot = cli_mod.run_image_check(
        image=image_path,
        source=tmp_path,
        print_tree=True,
        expected_crc32=0x1234,
        expected_manifest_sha256="a" * 64,
        emit_report=True,
    )

    assert errors == []
    assert warnings == []
    assert tree == {0: []}
    assert uroot == 0


def test_info_run_with_header(monkeypatch: pytest.MonkeyPatch) -> None:
    info_result: PFSImageInfo = PFSImageInfo(image=Path("image.ffpfs"))
    info_result.header = SimpleNamespace(version=0, block_size=65536, magic=0xABCD)
    monkeypatch.setattr(cli_mod, "read_pfs_info", lambda _image: info_result)
    assert cli_mod.cli_mkpfs_info_run(args=SimpleNamespace(image="image.ffpfs")) == 0


def test_extract_run_returns_1_on_result_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result = PFSExtractionResult(image=Path("image.ffpfs"), output_path=tmp_path / "out")
    result.errors.append("failed")
    monkeypatch.setattr(cli_mod, "extract_pfs_image", lambda **_kwargs: result)
    args = SimpleNamespace(image="image.ffpfs", output=str(tmp_path / "out"), overwrite=True)
    assert cli_mod.cli_mkpfs_extract_run(args=args) == 1


def test_main_dispatches_info(monkeypatch: pytest.MonkeyPatch) -> None:
    info_result: PFSImageInfo = PFSImageInfo(image=Path("image.ffpfs"))
    monkeypatch.setattr(cli_mod, "read_pfs_info", lambda _image: info_result)
    assert cli_mod.main(argv=["info", "--image", "image.ffpfs"]) == 0


def test_logging_supports_utf8_and_icon_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MKPFS_NO_UTF8", raising=False)

    class DummyStdout:
        encoding = "ascii"

    monkeypatch.setattr(mkp_logging.sys, "stdout", DummyStdout())
    assert mkp_logging._supports_utf8() is False
    assert mkp_logging._icon("info") == "INFO"

    class DummyStdoutUtf8:
        encoding = "utf-8"

    monkeypatch.setattr(mkp_logging.sys, "stdout", DummyStdoutUtf8())
    assert mkp_logging._supports_utf8() is True
    assert mkp_logging._icon("unknown") == ""


def test_logging_supports_utf8_false_when_no_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MKPFS_NO_UTF8", raising=False)

    class DummyStdoutNoEncoding:
        encoding = ""

    monkeypatch.setattr(mkp_logging.sys, "stdout", DummyStdoutNoEncoding())
    assert mkp_logging._supports_utf8() is False


def test_create_args_to_legacy_argv_compress_and_case_insensitive() -> None:
    args = SimpleNamespace(
        path="src",
        output="out.ffpfs",
        no_compress=False,
        threshold_gain=15,
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
    )
    argv: list[str] = cli_mod.create_args_to_legacy_argv(args=args)
    assert "--compress" in argv
    assert "--case-insensitive" in argv


def test_print_summary_when_compression_disabled(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    stats: BuildStats = BuildStats(input_path=tmp_path / "src", output_path=tmp_path / "out.ffpfs")
    stats.compression_enabled = False
    stats.total_files = 0
    cli_mod.print_summary(stats=stats)
    captured = capsys.readouterr()
    assert "Compression:             disabled" in captured.out


def test_create_run_invalid_block_and_level_and_cancel(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    src: Path = tmp_path / "src"
    src.mkdir()
    args = SimpleNamespace(
        path=str(src),
        output=str(tmp_path / "out"),
        no_compress=False,
        threshold_gain=20,
        block_size=12345,
        version="PS4",
        inode_bits=32,
        case_sensitive=False,
        case_insensitive=True,
        cpu_count=0,
        compression_level=9,
        signed=False,
        verbose=False,
        dry_run=True,
        verify=False,
    )
    monkeypatch.setattr(cli_mod, "validate_input", lambda _path: ("TITLE", []))
    with pytest.raises(BuildError):
        cli_mod.cli_mkpfs_create_run(args=args)

    args.block_size = 2048
    with pytest.raises(BuildError):
        cli_mod.cli_mkpfs_create_run(args=args)

    args.block_size = "auto"
    args.compression_level = 10
    with pytest.raises(BuildError):
        cli_mod.cli_mkpfs_create_run(args=args)

    args.compression_level = 9
    args.dry_run = False
    args.verify = False
    monkeypatch.setattr(cli_mod, "prompt_overwrite", lambda _p: False)
    monkeypatch.setattr(
        cli_mod, "build_pfs", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should not build"))
    )
    assert cli_mod.cli_mkpfs_create_run(args=args) == 0


def test_create_run_verify_with_warnings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    src: Path = tmp_path / "src"
    src.mkdir()
    out_path: Path = tmp_path / "out.ffpfs"
    args = SimpleNamespace(
        path=str(src),
        output=str(out_path),
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
    monkeypatch.setattr(cli_mod, "validate_input", lambda _path: ("TITLE", []))
    monkeypatch.setattr(cli_mod, "prompt_overwrite", lambda _p: True)
    monkeypatch.setattr(cli_mod, "build_pfs", lambda **_kwargs: BuildStats(input_path=src, output_path=out_path))
    monkeypatch.setattr(cli_mod, "run_image_check", lambda *_a, **_k: ([], ["warn-1"], {}, -1))
    assert cli_mod.cli_mkpfs_create_run(args=args) == 0


def test_check_run_invalid_crc_length_and_manifest() -> None:
    args_crc = SimpleNamespace(
        image="image.ffpfs",
        source=None,
        expected_crc32="0x123456789",
        expected_manifest_sha256=None,
        print_tree=False,
    )
    assert cli_mod.cli_mkpfs_check_run(args=args_crc) == 2

    args_manifest = SimpleNamespace(
        image="image.ffpfs",
        source=None,
        expected_crc32=None,
        expected_manifest_sha256="abc",
        print_tree=False,
    )
    assert cli_mod.cli_mkpfs_check_run(args=args_manifest) == 2


def test_analyze_crc_parse_error_and_warning_output(monkeypatch: pytest.MonkeyPatch) -> None:
    args_bad_crc = SimpleNamespace(
        image="img",
        source=None,
        expected_crc32="zz",
        expected_manifest_sha256=None,
        print_tree=False,
    )
    assert cli_mod.cli_mkpfs_analyze_run(args=args_bad_crc) == 2

    inspection: PFSImageInspection = PFSImageInspection(image=Path("img"))
    inspection.header = SimpleNamespace(version=0, block_size=65536)
    inspection.warnings = ["warning-1"]
    inspection.errors = []
    monkeypatch.setattr(cli_mod, "inspect_pfs_image", lambda **_kwargs: inspection)
    args_ok = SimpleNamespace(
        image="img",
        source=None,
        expected_crc32=None,
        expected_manifest_sha256="a" * 64,
        print_tree=False,
    )
    assert cli_mod.cli_mkpfs_analyze_run(args=args_ok) == 0


def test_analyze_crc_with_0x_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    inspection: PFSImageInspection = PFSImageInspection(image=Path("img"))
    inspection.header = SimpleNamespace(version=0, block_size=65536)
    inspection.warnings = []
    inspection.errors = []
    monkeypatch.setattr(cli_mod, "inspect_pfs_image", lambda **_kwargs: inspection)

    args = SimpleNamespace(
        image="img",
        source=None,
        expected_crc32="0x1A2B",
        expected_manifest_sha256=None,
        print_tree=False,
    )
    assert cli_mod.cli_mkpfs_analyze_run(args=args) == 0


def test_extract_run_with_warnings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result: PFSExtractionResult = PFSExtractionResult(image=Path("image.ffpfs"), output_path=tmp_path / "out")
    result.warnings.append("warn")
    monkeypatch.setattr(cli_mod, "extract_pfs_image", lambda **_kwargs: result)
    args = SimpleNamespace(image="image.ffpfs", output=str(tmp_path / "out"), overwrite=True)
    assert cli_mod.cli_mkpfs_extract_run(args=args) == 0


def test_run_image_check_mismatch_and_orphan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_path: Path = tmp_path / "image.ffpfs"
    image_path.write_bytes(b"x")

    header = SimpleNamespace(mode=0, version=0, magic=123, readonly=1, block_size=65536)
    inodes = [
        SimpleNamespace(number=0, is_compressed=False, size=10, size_compressed=10),
        SimpleNamespace(number=99, is_compressed=False, size=10, size_compressed=10),
    ]

    monkeypatch.setattr(cli_mod, "parse_image_header", lambda _fh: header)
    monkeypatch.setattr(cli_mod, "parse_image_inodes", lambda _fh, _header: inodes)
    monkeypatch.setattr(cli_mod, "validate_inode_layout", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli_mod, "verify_signed_image_signatures", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli_mod, "parse_superroot_and_indexes", lambda *_args, **_kwargs: (0, {1: 2}, {}, {0}))
    monkeypatch.setattr(
        cli_mod, "build_tree_from_uroot", lambda *_args, **_kwargs: ({"file.bin": 0}, {"": 0}, {0: []})
    )
    monkeypatch.setattr(cli_mod, "build_expected_fpt", lambda *_args, **_kwargs: {1: []})
    monkeypatch.setattr(cli_mod, "validate_fpt_maps", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli_mod, "validate_ps5_checklist", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli_mod, "verify_file_payload_hashes", lambda *_args, **_kwargs: (1, 0x1111, "b" * 64))

    errors, warnings, _tree, _uroot = cli_mod.run_image_check(
        image=image_path,
        source=None,
        print_tree=False,
        expected_crc32=0x2222,
        expected_manifest_sha256="a" * 64,
        emit_report=False,
    )

    assert warnings == []
    assert any("CRC32 mismatch" in error_text for error_text in errors)
    assert any("Manifest SHA256 mismatch" in error_text for error_text in errors)
    assert any("orphan inodes" in error_text for error_text in errors)
