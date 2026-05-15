# Development Guidelines

This document contains critical information about working with this codebase.
Follow these guidelines precisely.

## Rules

1. Package Management
   - ONLY use uv, NEVER pip
   - Installation: `uv add package`
   - Upgrading: `uv add --dev package --upgrade-package package`
   - FORBIDDEN: `uv pip install`, `@latest` syntax

2. Code Quality
   - Type hints required for all code
   - Follow existing patterns exactly
   - Use Google style for docstring
   - Prefer explicit keyword arguments when calling functions or instantiating classes in Python; avoid relying on parameter ordering.
   - All functions must include pydocs (Google style) describing what the function does, its parameters, return value(s), and any raised exceptions.

3. Testing Requirements
   - Framework: `uv run --frozen pytest`
   - run ./run-tests.sh for convenience
   - Coverage: test edge cases and errors
   - New features require tests
   - Bug fixes require regression tests
   - Release validation should build the package and run `twine check` before publish

4. Temporary Artifacts and Reports
   - Use `./tmp/` for scratch files, planning notes, generated HTML reports, and other transient outputs.
   - Keep `./tmp/` out of commits.
   - For detailed research or long-form answers, provide the normal text response and also save a companion HTML report under `./tmp/` with a clickable file path.

5. Git
   - Follow the Conventional Commits style on commit messages.


## Code Formatting and Linting

1. Ruff
   - Format: `uv run --frozen ruff format .`
   - Check: `uv run --frozen ruff check .`
   - Fix: `uv run --frozen ruff check . --fix`
2. Pre-commit
   - Config: `.pre-commit-config.yaml`
   - Runs: on git commit
   - Tools: Ruff (Python)

3. Type annotations (project preference)
   - The project targets Python 3.11: prefer built-in generic types (list, dict, tuple, set) instead of typing.List/Dict/Tuple/Set.
   - Use the `X | None` union form instead of `Optional[X]` where appropriate.
   - Add type hints ALL variables and functions in this project.

## GitHub CLI Tips

When using `gh` command in terminal automation:
- **Disable pager to avoid interactive prompts**: Use `GH_PAGER=cat gh <command>` to prevent pager from opening and blocking terminal execution
- **Export logs to file**: `GH_PAGER=cat gh run view <run-id> > output.txt 2>&1` to capture full output without interactive delays
- **Check workflow status**: `GH_PAGER=cat gh run view <run-id> --json conclusion,status` for structured status data
- Default: `gh` commands may open `less` pager, which opens the alternate terminal buffer and blocks async execution
- **GIT_PAGER** also opens alternate buffer — use `GIT_PAGER='' git <command>` to suppress for git commands
- **Prefer Python subprocess** for automation that requires capturing output reliably: `subprocess.run(['gh', ...], capture_output=True, text=True, env={**os.environ, 'GH_PAGER': 'cat'})`

## Writing style preference

When writing in natural language README, docs, comments, or wiki pages, avoid using the em dash (—). Prefer commas, hyphens, 'title: subtitle' structure, or a semicolon to separate related ideas and maintain consistent punctuation across project documentation in the same paragraph.
