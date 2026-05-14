"""Utilities shared between builder and analyzer.

Contains small helpers extracted from legacy ffpfs.py and analyze_pfs.py.
"""

from pathlib import Path
from typing import BinaryIO


def human_readable_size(size: int) -> str:
    """Convert bytes to human-readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def ceil_div(a: int, b: int) -> int:
    """Integer ceiling division."""
    return (a + b - 1) // b


def is_power_of_two(v: int) -> bool:
    """Return True if v is a positive power of two."""
    return v > 0 and (v & (v - 1)) == 0


def normalize_output_path(path_arg: str) -> tuple[Path, str | None]:
    """Normalize output path and ensure .ffpfs extension.

    Returns (Path, warning_message_or_None).
    """
    p = Path(path_arg)
    if p.suffix.lower() == ".ffpfs":
        return p, None
    normalized = p.with_suffix(".ffpfs")
    return normalized, f"Output extension changed to .ffpfs (was {p.suffix or '<none>'})"


def read_param_json(path: Path) -> dict[str, object]:
    """Read a JSON file and return parsed object.

    Raises a ValueError on parse errors.
    """
    import json

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:  # pragma: no cover - bubble up
        raise ValueError(f"Failed to parse {path}: {exc}") from exc


def _read_exact(fh: BinaryIO, offset: int, size: int) -> bytes:
    """Read ``size`` bytes from file handle starting at ``offset``.

    Raises ValueError on truncated read.
    """
    fh.seek(offset)
    data = fh.read(size)
    if len(data) != size:
        raise ValueError(f"truncated read at offset {offset} (wanted {size}, got {len(data)})")
    return data
