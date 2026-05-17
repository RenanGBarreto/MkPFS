"""Shared test fixture builders for parity tests."""

import json
from pathlib import Path


def make_minimal_app(tmp_path: Path) -> Path:
    """Create minimal valid app tree under tmp_path/app/.

    Creates an app directory with sce_sys/param.json and eboot.bin
    required for PFS image creation.

    Args:
        tmp_path: Temporary directory path.

    Returns:
        Path to the created app directory.
    """
    app: Path = tmp_path / "app"
    sce: Path = app / "sce_sys"
    sce.mkdir(parents=True)
    (sce / "param.json").write_text(json.dumps({"titleId": "NPXS99999"}), encoding="utf-8")
    (app / "eboot.bin").write_bytes(b"\x00" * 128)
    return app


def make_app_with_nested_dirs(tmp_path: Path) -> Path:
    """Create app tree with nested dirs and several files for FPT/tree coverage.

    Creates a more complex directory structure with subdirectories and multiple
    files to test flat path table and tree handling.

    Args:
        tmp_path: Temporary directory path.

    Returns:
        Path to the created app directory.
    """
    app: Path = tmp_path / "app"
    sce: Path = app / "sce_sys"
    sce.mkdir(parents=True)
    (sce / "param.json").write_text(json.dumps({"titleId": "NPXS99999"}), encoding="utf-8")
    (app / "eboot.bin").write_bytes(b"x" * 200)
    sub: Path = app / "data" / "levels"
    sub.mkdir(parents=True)
    (sub / "level1.bin").write_bytes(b"L" * 300)
    (sub / "level2.bin").write_bytes(b"M" * 400)
    (app / "data" / "config.json").write_text('{"v":1}', encoding="utf-8")
    return app
