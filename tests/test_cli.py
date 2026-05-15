import argparse
import builtins
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import mkpfs.cli as cli
from mkpfs import utils
from mkpfs.pbar import Progress


def test_human_readable_size_pb() -> None:
    # Choose a value large enough to reach PB branch
    assert "PB" in utils.human_readable_size(1024**5)


def test_progress_speed_and_eta(capsys: pytest.CaptureFixture[str]) -> None:
    p = Progress(enabled=True)
    # Simulate a previous start time so elapsed > 0.1
    p.phase_start_time["compress"] = time.time() - 2.0
    p.phase_bytes["compress"] = 1024 * 1024
    # First call: bytes_processed > 0 triggers bytes speed branch
    p.step("compress", 1, 4, bytes_processed=1024 * 1024)
    # Now test item/s branch by calling with bytes_processed == 0
    p.phase_start_time["walk"] = time.time() - 1.0
    p.step("walk", 1, 10, bytes_processed=0)
    _out, err = capsys.readouterr()
    assert "ETA" in err or "items/s" in err


def test_parse_args_basic() -> None:
    ns = cli.parse_args(["--path", "src", "--output", "out.ffpfs"])
    assert isinstance(ns, argparse.Namespace)


def test_create_args_to_legacy_argv() -> None:
    args = SimpleNamespace(
        path="/p",
        output="/o",
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
    )
    argv = cli.create_args_to_legacy_argv(args)
    assert "--path" in argv
    assert "--output" in argv


def test_prompt_overwrite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    f = tmp_path / "out.ffpfs"
    f.write_text("")
    # simulate user entering 'n'
    monkeypatch.setattr(builtins, "input", lambda prompt="": "n")
    assert not cli.prompt_overwrite(f)
    # simulate 'y'
    monkeypatch.setattr(builtins, "input", lambda prompt="": "y")
    assert cli.prompt_overwrite(f)


def make_buildstats_obj(tmp_path: Path) -> object:
    class BS:
        pass

    b = BS()
    b.input_path = tmp_path
    b.output_path = tmp_path / "out.ffpfs"
    b.total_files = 0
    b.uncompressed_total_size = 0
    b.stored_total_size = 0
    b.compression_enabled = False
    b.compressed_files = 0
    b.uncompressed_files = 0
    b.actual_gain_pct = 0.0
    b.max_possible_gain_pct = 0.0
    b.all_compressed_total_size = 0
    b.block_alignment_waste = 0
    b.block_size = 65536
    b.elapsed_seconds = 0.01
    return b


def test_cli_mkpfs_create_run_monkeypatched(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    args = SimpleNamespace(
        path=str(tmp_path),
        output=str(tmp_path / "out"),
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
        dry_run=True,
        no_compress=False,
    )

    # monkeypatch validate_input and build_pfs and normalize_output_path
    monkeypatch.setattr(cli, "validate_input", lambda p: (None, []))
    monkeypatch.setattr(cli, "build_pfs", lambda **kw: make_buildstats_obj(tmp_path))
    monkeypatch.setattr(cli, "normalize_output_path", lambda p: (Path(p), None))
    monkeypatch.setattr(cli, "prompt_overwrite", lambda p: True)

    # dry_run True should return 0
    rc = cli.cli_mkpfs_create_run(args)
    assert rc == 0


def test_cli_mkpfs_check_and_ls_and_info_and_analyze_and_extract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Prepare a dummy image file
    image = tmp_path / "img.ffpfs"
    image.write_bytes(b"data")

    # run_image_check should return no errors for ls
    monkeypatch.setattr(cli, "run_image_check", lambda *a, **k: ([], [], {}, 0))
    args_ls = SimpleNamespace(image=str(image))
    assert cli.cli_mkpfs_ls_run(args_ls) == 0

    # check run with bad expected CRC
    args_check = SimpleNamespace(
        image=str(image), source=None, expected_crc32=None, expected_manifest_sha256=None, print_tree=False
    )
    # monkeypatch run_image_check used in check
    monkeypatch.setattr(cli, "run_image_check", lambda *a, **k: ([], [], {}, 0))
    assert cli.cli_mkpfs_check_run(args_check) == 0

    # info run
    class InfoRes:
        pass

    infoobj = InfoRes()
    infoobj.size_bytes = 123
    infoobj.header = None
    infoobj.version_label = "PS4"
    infoobj.warnings = []
    infoobj.errors = []
    monkeypatch.setattr(cli, "read_pfs_info", lambda image: infoobj)
    args_info = SimpleNamespace(image=str(image))
    assert cli.cli_mkpfs_info_run(args_info) == 0

    # analyze run
    class InspectRes:
        pass

    ires = InspectRes()
    ires.header = SimpleNamespace(version=2)
    ires.header.block_size = 65536
    ires.warnings = []
    ires.errors = []
    ires.has_tree = False
    ires.dirents_by_inode = {}
    ires.uroot_inode = 0
    monkeypatch.setattr(cli, "inspect_pfs_image", lambda **k: ires)
    args_an = SimpleNamespace(
        image=str(image), source=None, expected_crc32=None, expected_manifest_sha256=None, print_tree=False
    )
    assert cli.cli_mkpfs_analyze_run(args_an) == 0

    # extract run
    class ExtractRes:
        pass

    xres = ExtractRes()
    xres.warnings = []
    xres.errors = []
    xres.output_path = tmp_path
    xres.files_written = 0
    xres.directories_created = 0
    xres.bytes_written = 0
    monkeypatch.setattr(cli, "extract_pfs_image", lambda **k: xres)
    args_ex = SimpleNamespace(image=str(image), output=str(tmp_path / "out"), overwrite=True)
    assert cli.cli_mkpfs_extract_run(args_ex) == 0
