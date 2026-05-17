import subprocess
import sys
from contextlib import redirect_stdout
from io import StringIO

import pytest

from mkpfs.cli import cli_mkpfs


def test_cli_help_shows_top_description() -> None:
    """Top-level help message displays project description."""
    buffer = StringIO()
    with pytest.raises(SystemExit) as excinfo, redirect_stdout(buffer):
        cli_mkpfs(["-h"])

    assert excinfo.value.code == 0
    assert "PFS create/check/list CLI" in buffer.getvalue()


def test_verify_alias_exists() -> None:
    """'verify' must be an accepted alias for the check subcommand."""
    result = subprocess.run([sys.executable, "-m", "mkpfs", "verify", "--help"], capture_output=True, text=True)
    assert result.returncode == 0, f"verify --help failed: {result.stderr}"
    # Alias help shows check's signature and arguments
    assert "--image" in result.stdout


def test_check_help_command() -> None:
    """'check' subcommand help displays expected arguments."""
    result = subprocess.run([sys.executable, "-m", "mkpfs", "check", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--image" in result.stdout
    assert "--source" in result.stdout
