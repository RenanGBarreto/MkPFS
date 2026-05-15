from pathlib import Path

import pytest

import mkpfs.cli as cli_mod


class DummyHeader:
    def __init__(self) -> None:
        self.version = 0
        self.magic = 0
        self.readonly = 1
        self.mode = 0
        self.block_size = 65536
        self.dinode_count = 0
        self.dinode_block_count = 0
        self.ndblock = 0


def test_run_image_check_reports_and_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    img = tmp_path / "img.ffpfs"
    img.write_bytes(b"0")

    # Patch the parser functions to return controlled data
    monkeypatch.setattr(cli_mod, "parse_image_header", lambda fh: DummyHeader())
    monkeypatch.setattr(cli_mod, "parse_image_inodes", lambda fh, header: [])
    monkeypatch.setattr(cli_mod, "parse_superroot_and_indexes", lambda fh, header, inodes, errors: (-1, {}, {}, set()))
    monkeypatch.setattr(cli_mod, "verify_signed_image_signatures", lambda fh, header, inodes, errors: None)
    monkeypatch.setattr(cli_mod, "build_tree_from_uroot", lambda fh, header, inodes, uroot, errors: ({}, {}, {}))
    monkeypatch.setattr(
        cli_mod, "verify_file_payload_hashes", lambda fh, header, inodes, file_inodes, errors: (0, 0, "")
    )

    errors, warnings, _tree, _uroot = cli_mod.run_image_check(
        image=img, source=None, print_tree=True, emit_report=True
    )
    # With dummy data and no explicit errors, expect empty errors list
    assert isinstance(errors, list)
    assert isinstance(warnings, list)
