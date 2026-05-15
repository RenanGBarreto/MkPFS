import time
from pathlib import Path

import pytest

from mkpfs import utils
from mkpfs.pbar import Progress
from mkpfs.pfs import scan_source_tree


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
    p.status("status-line")
    _out, err = capsys.readouterr()
    assert "ETA" in err or "items/s" in err


def test_progress_step_no_output(capsys: pytest.CaptureFixture[str]) -> None:
    p = Progress(enabled=False)
    # Should be no error when progress disabled
    p.step("scan", 1, 10, bytes_processed=100)
    p.status("status msg")
    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""


def test_progress_step_enabled(capsys: pytest.CaptureFixture[str]) -> None:
    p = Progress(enabled=True, width=10)
    p.step("scan", 1, 2, bytes_processed=100)
    p.step("scan", 2, 2, bytes_processed=200)
    _out, err = capsys.readouterr()
    # Should have progress written to stderr
    assert "%" in err


def test_scan_source_tree(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir()
    (root / "a").mkdir()
    (root / "a" / "file1.txt").write_text("x")
    (root / "b").mkdir()
    (root / "b" / "file2.txt").write_text("y")

    p = Progress(enabled=False)
    dirs, files, total = scan_source_tree(root, p)
    assert total == 2
    assert "a/file1.txt" in files
    assert "b/file2.txt" in files
    assert "a" in dirs
    assert "b" in dirs
