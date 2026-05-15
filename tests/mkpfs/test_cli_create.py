import json
import multiprocessing as mp
from pathlib import Path
from types import SimpleNamespace

import pytest

from mkpfs.cli import cli_mkpfs_create_run
from mkpfs.pfs import BuildError, BuildStats


def make_valid_source(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    sce = src / "sce_sys"
    sce.mkdir()
    param = sce / "param.json"
    param.write_text(json.dumps({"titleId": "ABC123"}))
    # recommended file
    (src / "eboot.bin").write_text("x")
    return src


def test_cli_create_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    src = make_valid_source(tmp_path)
    out = tmp_path / "out.img"

    # Patch build_pfs to avoid heavy work and return a minimal BuildStats
    def fake_build_pfs(*args: object, **kwargs: object) -> BuildStats:
        return BuildStats(input_path=src, output_path=out)

    monkeypatch.setattr("mkpfs.cli.build_pfs", fake_build_pfs)

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
        dry_run=True,
        verify=False,
    )

    rc = cli_mkpfs_create_run(args)
    assert rc == 0


def test_cli_create_invalid_threshold(tmp_path: Path) -> None:
    src = make_valid_source(tmp_path)
    out = tmp_path / "out.img"
    args = SimpleNamespace(
        path=str(src),
        output=str(out),
        no_compress=False,
        threshold_gain=-1,
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
        verify=False,
    )
    with pytest.raises(BuildError):
        cli_mkpfs_create_run(args)


def test_cli_create_invalid_block_size(tmp_path: Path) -> None:
    src = make_valid_source(tmp_path)
    out = tmp_path / "out.img"
    args = SimpleNamespace(
        path=str(src),
        output=str(out),
        no_compress=False,
        threshold_gain=20,
        block_size="not-an-int",
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
    with pytest.raises(BuildError):
        cli_mkpfs_create_run(args)


def test_cli_create_invalid_cpu_count(tmp_path: Path) -> None:
    src = make_valid_source(tmp_path)
    out = tmp_path / "out.img"
    available = mp.cpu_count()
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
        cpu_count=available + 10,
        compression_level=9,
        signed=False,
        verbose=False,
        dry_run=True,
        verify=False,
    )
    with pytest.raises(BuildError):
        cli_mkpfs_create_run(args)
