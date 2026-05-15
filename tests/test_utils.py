import json
from io import BytesIO
from pathlib import Path

import pytest

from mkpfs import utils


def test_human_readable_size() -> None:
    assert utils.human_readable_size(0).startswith("0.00")
    assert "KB" in utils.human_readable_size(1024)
    assert "MB" in utils.human_readable_size(1024 * 1024)


def test_ceil_div() -> None:
    assert utils.ceil_div(1, 1) == 1
    assert utils.ceil_div(3, 2) == 2
    assert utils.ceil_div(0, 5) == 0


def test_is_power_of_two() -> None:
    assert utils.is_power_of_two(1)
    assert utils.is_power_of_two(2)
    assert not utils.is_power_of_two(0)
    assert not utils.is_power_of_two(3)


def test_normalize_output_path(tmp_path: Path) -> None:
    p, warn = utils.normalize_output_path(str(tmp_path / "out.FFPFS"))
    assert p.suffix.lower() == ".ffpfs"
    # When the input already has an ffpfs-like suffix (case-insensitive) we
    # expect no warning because the normalized path keeps the same extension.
    assert warn is None

    p2, warn2 = utils.normalize_output_path(str(tmp_path / "image.ffpfs"))
    assert p2.suffix == ".ffpfs"
    assert warn2 is None


def test_read_param_json(tmp_path: Path) -> None:
    f = tmp_path / "params.json"
    f.write_text(json.dumps({"a": 1}), encoding="utf-8")
    data = utils.read_param_json(f)
    assert data["a"] == 1

    # Invalid JSON raises ValueError
    bad = tmp_path / "bad.json"
    bad.write_text("notjson", encoding="utf-8")
    with pytest.raises(ValueError):
        utils.read_param_json(bad)


def test__read_exact() -> None:
    b = BytesIO(b"0123456789")
    # read 4 bytes at offset 2
    result = utils._read_exact(b, 2, 4)
    assert result == b"2345"

    # truncated read raises
    b2 = BytesIO(b"abc")
    with pytest.raises(ValueError):
        utils._read_exact(b2, 0, 10)
