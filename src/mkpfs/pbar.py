"""Progress / progress-bar helpers extracted from psf.py.

This module contains the Progress class and scan_source_tree implementation
copied from psf.py so psf can be simplified. Keep behavior identical; imports
refer to psf.consts and the repo's types where necessary.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .utils import human_readable_size

if TYPE_CHECKING:
    from .pfs import DirNode, FileNode


class Progress:
    def __init__(self, enabled: bool = True, width: int = 32) -> None:
        self.enabled = enabled
        self.width = width
        self.last_phase = None
        self.phase_start_time = {}
        self.phase_bytes = {}  # Track bytes processed per phase
        self.phase_last_len = {}  # Track last written line length per phase

    def step(self, phase: str, done: int, total: int, bytes_processed: int = 0) -> None:
        if not self.enabled:
            return

        # Initialize phase tracking if needed
        if phase not in self.phase_start_time:
            self.phase_start_time[phase] = time.time()
            self.phase_bytes[phase] = 0

        if bytes_processed > 0:
            self.phase_bytes[phase] = bytes_processed

        total = max(total, 1)
        done = max(0, min(done, total))
        ratio = done / total
        fill = int(self.width * ratio)
        bar = "#" * fill + "-" * (self.width - fill)
        pct = int(ratio * 100)

        # Calculate speed and ETA
        elapsed = time.time() - self.phase_start_time[phase]
        speed_str = ""
        eta_str = ""

        if elapsed > 0.1 and done > 0:
            if bytes_processed > 0:
                speed = self.phase_bytes[phase] / elapsed
                speed_str = f" @ {human_readable_size(int(speed))}/s"
                if done < total:
                    remaining_bytes = (self.phase_bytes[phase] / done) * (total - done)
                    eta_secs = remaining_bytes / speed if speed > 0 else 0
                    eta_str = f" ETA {int(eta_secs)}s" if eta_secs < 3600 else f" ETA {eta_secs / 60:.1f}m"
            else:
                speed = done / elapsed
                speed_str = f" {speed:.1f} items/s"
                if done < total:
                    eta_secs = (total - done) / speed if speed > 0 else 0
                    eta_str = f" ETA {int(eta_secs)}s" if eta_secs < 3600 else f" ETA {eta_secs / 60:.1f}m"

        line = f"[{bar}] {pct:3d}% {phase}{speed_str}{eta_str}"
        last_len = self.phase_last_len.get(phase, 0)
        padding = max(0, last_len - len(line))
        sys.stderr.write(f"\r{line}{' ' * padding}")
        self.phase_last_len[phase] = len(line)
        if done >= total:
            sys.stderr.write("\n")
            # Reset phase tracking
            self.phase_start_time.pop(phase, None)
            self.phase_bytes.pop(phase, None)
            self.phase_last_len.pop(phase, None)
        sys.stderr.flush()
        self.last_phase = phase

    def status(self, message: str) -> None:
        """Print a status message without progress bar."""
        if not self.enabled:
            return
        sys.stderr.write(message + "\n")
        sys.stderr.flush()


def scan_source_tree(root: Path, progress: Progress) -> tuple[dict[str, DirNode], dict[str, FileNode], int]:
    progress.status("\nDiscovering files...")
    abs_files = [p for p in root.rglob("*") if p.is_file()]
    abs_files.sort(key=lambda p: p.relative_to(root).as_posix().lower())

    dirs: dict[str, DirNode] = {"": DirNode(rel_dir="", name="uroot", parent_rel_dir=None)}
    files: dict[str, FileNode] = {}

    total = len(abs_files)
    total_bytes = 0
    for i, abs_path in enumerate(abs_files, start=1):
        rel = abs_path.relative_to(root).as_posix()
        parent = str(Path(rel).parent.as_posix())
        if parent == ".":
            parent = ""
        parts = list(Path(rel).parts[:-1])

        curr = ""
        for part in parts:
            next_rel = f"{curr}/{part}" if curr else part
            if next_rel not in dirs:
                dirs[next_rel] = DirNode(rel_dir=next_rel, name=part, parent_rel_dir=curr if curr != "" else "")
                dirs[curr].children_dirs.append(next_rel)
            curr = next_rel

        if parent not in dirs:
            # This should not happen but keep it robust.
            dirs[parent] = DirNode(rel_dir=parent, name=Path(parent).name if parent else "uroot", parent_rel_dir="")

        name = Path(rel).name
        raw_size = abs_path.stat().st_size
        total_bytes += raw_size
        file_node = FileNode(
            rel_path=rel,
            abs_path=abs_path,
            parent_rel_dir=parent,
            name=name,
            raw_size=raw_size,
        )
        files[rel] = file_node
        dirs[parent].children_files.append(rel)
        progress.step("scan", i, total, bytes_processed=total_bytes)

    for d in dirs.values():
        d.children_dirs.sort(key=str.lower)
        d.children_files.sort(key=str.lower)

    return dirs, files, total
