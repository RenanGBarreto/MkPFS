"""MKPFS CLI main() hook.

Expose a module-level :func:`main` compatible with older tests and tools.
"""

from mkpfs.cli import cli_mkpfs_main


def main(argv: list[str] | None = None) -> int:
    """Entrypoint used by CLI tests.

    Args:
        argv: Optional argument vector. When omitted, sys.argv is used by
            the argument parser.

    Returns:
        The integer exit code from the CLI handler.
    """
    # Delegate to the canonical CLI main function which is easier to patch in
    # tests and older tooling.
    return cli_mkpfs_main(argv)


# When executed as a script, run the main entrypoint.
if __name__ == "__main__":
    raise SystemExit(main())
