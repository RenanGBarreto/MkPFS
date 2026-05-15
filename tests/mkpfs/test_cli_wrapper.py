import argparse

import pytest

import mkpfs.cli as cli


def test_cli_mkpfs_compat_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify the legacy ``cli_mkpfs`` wrapper delegates to the parser's func.

    This test replaces the parser factory with a minimal parser that defines a
    single subcommand whose handler returns a known value. Calling
    ``cli.cli_mkpfs(['noop'])`` should return that value.
    """
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    noop = sub.add_parser("noop")

    def handler(_args: argparse.Namespace) -> int:
        return 123

    noop.set_defaults(func=handler)

    monkeypatch.setattr(cli, "cli_mkpfs_main_parsers", lambda: parser)

    result = cli.cli_mkpfs(["noop"])
    assert result == 123
