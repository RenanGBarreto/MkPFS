from contextlib import redirect_stdout
from io import StringIO

import pytest

from mkpfs.__main__ import main


def test_main() -> None:
    buffer = StringIO()
    with pytest.raises(SystemExit) as excinfo, redirect_stdout(buffer):
        main(["-h"])

    assert excinfo.value.code == 0
    assert "PFS create/check/list CLI" in buffer.getvalue()
