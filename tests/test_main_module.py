import runpy

import pytest

import mkpfs.cli as cli


def test___main___executes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "cli_mkpfs_main", lambda argv=None: 0)
    monkeypatch.setattr(cli, "cli_mkpfs", lambda argv=None: 0)
    # Execute the module as __main__ to cover the __main__ entrypoint. The
    # entrypoint raises SystemExit with the result of `main()` which we stub
    # to return 0, so assert that behaviour.
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("mkpfs.__main__", run_name="__main__")
    assert exc.value.code == 0
