from contextlib import redirect_stdout
from io import StringIO

from mkpfs.__main__ import main


def test_main() -> None:
    buffer = StringIO()
    with redirect_stdout(buffer):
        main()

    assert buffer.getvalue() == "Hello from mkpfs!\n"
