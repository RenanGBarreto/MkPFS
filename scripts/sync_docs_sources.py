"""Synchronize reusable knowledge-base sources into the MkDocs tree.

This keeps the canonical long-form markdown under ``related-projects/`` while
exposing stable docs paths for MkDocs. The script prefers symlinks so the site
can reuse the original files without duplicating content, and falls back to
copying if the platform does not permit symlink creation.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = ROOT / "docs"
SOURCE_ROOT = ROOT / "related-projects"
ASSET_ROOT = ROOT / "assets" / "images"
TARGET_ROOT = DOCS_ROOT / "knowledge" / "sources"
ALLOWED_ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
IGNORED_NAMES = {".git", ".DS_Store", "__pycache__"}
DOCUMENTED_SOURCE_DIRS = {
    "liborbispkg",
    "liborbispkg-wiki",
    "pkgtool",
    "shadowmountplus",
}


def remove_path(path: Path) -> None:
    """Remove a file or symlink if it already exists."""
    if path.is_symlink() or path.exists():
        path.unlink()


def link_or_copy(source: Path, target: Path) -> str:
    """Create a symlink to a source file or copy it if symlinks fail."""
    target.parent.mkdir(parents=True, exist_ok=True)
    remove_path(target)

    relative_source = os.path.relpath(source, start=target.parent)
    try:
        target.symlink_to(relative_source)
        return "symlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def link_directory(source: Path, target: Path) -> str:
    """Create a directory symlink for a companion source tree."""
    target.parent.mkdir(parents=True, exist_ok=True)
    remove_path(target)
    relative_source = os.path.relpath(source, start=target.parent)
    target.symlink_to(relative_source, target_is_directory=True)
    return "symlink-dir"


def should_ignore(path: Path) -> bool:
    """Return True when a path should not be mirrored into the docs tree."""
    return path.name in IGNORED_NAMES or path.name.startswith(".")


def sync_asset_tree() -> None:
    """Expose the shared image assets inside the docs tree."""
    for asset in ASSET_ROOT.iterdir():
        if should_ignore(asset) or asset.suffix.lower() not in ALLOWED_ASSET_SUFFIXES:
            continue
        target = DOCS_ROOT / "assets" / "images" / asset.name
        mode = link_or_copy(asset, target)
        print(f"{mode}: {target} -> {asset}")


def sync_knowledge_sources() -> None:
    """Mirror the reusable knowledge sources into the docs tree."""
    for source in SOURCE_ROOT.iterdir():
        if should_ignore(source):
            continue

        target = TARGET_ROOT / source.name
        if source.is_dir():
            if source.name in DOCUMENTED_SOURCE_DIRS:
                mode = link_directory(source, target)
                print(f"{mode}: {target} -> {source}")
        elif source.suffix.lower() == ".md":
            mode = link_or_copy(source, target)
            print(f"{mode}: {target} -> {source}")


def main() -> int:
    """Synchronize all configured knowledge-base sources."""
    sync_asset_tree()
    sync_knowledge_sources()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
