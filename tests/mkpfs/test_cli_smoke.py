from contextlib import redirect_stdout
from io import StringIO

import pytest

from mkpfs.cli import cli_mkpfs


def test_cli_help_shows_top_description() -> None:
    buffer = StringIO()
    with pytest.raises(SystemExit) as excinfo, redirect_stdout(buffer):
        cli_mkpfs(["-h"])

    assert excinfo.value.code == 0
    assert "PFS create/check/list CLI" in buffer.getvalue()
