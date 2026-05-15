import sys

import pytest

import mkpfs.logging as mlogging


def test_supports_utf8_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MKPFS_NO_UTF8", "1")
    assert not mlogging.supports_utf8()


def test_icon_ascii_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MKPFS_NO_UTF8", "1")
    assert mlogging.icon("info") == "INFO"


def test_icon_utf8_when_supported(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # Ensure env var not set and stdout encoding appears UTF-8
    monkeypatch.delenv("MKPFS_NO_UTF8", raising=False)

    class DummyOut:
        encoding = "utf-8"

    monkeypatch.setattr(sys, "stdout", DummyOut())
    assert mlogging.supports_utf8()
    glyph = mlogging.icon("ok")
    assert glyph != "OK"


def test_log_prints_to_stdout_and_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    mlogging.info("hello world", icon_name=None)
    mlogging.error("bad stuff", icon_name=None)
    out, err = capsys.readouterr()
    assert "hello world" in out
    assert "bad stuff" in err
