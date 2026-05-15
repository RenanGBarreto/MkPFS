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
   - Annotate all function and method signatures with types.
   - All local variables must have explicit type annotations at their definition site, even for simple literals. Examples: `count: int = 0`, `name: str = ""`.
   - Prefer built-in generic types and explicit variable annotations; avoid relying on implicit type inference for readability and static analysis.
   - Always reason if variables are nullable and select the appropriate type. Sometimes differentiating None from a 0 or empty string is the key to good code.

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

### `PFS` Capitalization Rule

- **Class / Symbol Names**: Use uppercase `PFS` (all three letters) when it appears inside class names, types, or other identifiers that use CamelCase or TitleCase. Examples: `PFSExtractionResult`, `PFSImageInfo`, `PFSOperationResult`.
- **Variables / Functions / snake_case**: Use lowercase `pfs` for variable names, function prefixes, and snake_case identifiers. Examples: `pfs_gen_sign_key`, `read_pfs_info`, `pfs_version`.
- **Never** use `Pfs` (mixed-case) — either `PFS` or `pfs` is correct depending on the context.

### Long-function block comments

- For functions that are long (roughly >30 lines) or that contain multiple logical phases, add a single-line comment above each major block explaining its purpose. Keep comments succinct and in present tense.
- These single-line comments are NOT a replacement for proper function docstrings; they should summarize the block intent (for example: `# Walk source tree and collect file metadata`).
- Prefer comments that clarify why a block exists or what it accomplishes, not restating what the code already shows.
