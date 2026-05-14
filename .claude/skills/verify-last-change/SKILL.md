---
name: verify-last-change
description: Run the repo test suite and inspect the latest change for regressions.
context: fork
---

# Verify Last Change

Use this skill when the user wants to double-check the last implemented feature or validate the latest change in this repo.

1. Identify the change scope.
   - Inspect `git status --short`.
   - If there is a recent commit, review `git show --stat --oneline HEAD` and `git diff HEAD~1..HEAD`.
   - Otherwise review `git diff --stat` and `git diff`.
2. Read the touched code and any related tests.
   - Confirm the intended behavior, edge cases, and failure paths.
   - Focus on the files that are actually related to the feature.
3. Run validation.
   - Default to `uv run --frozen pytest`.
   - Run `uv run --frozen ruff check .` when Python code changed or the diff touches imports, typing, or formatting-sensitive code.
   - Use `./run-tests.sh` only if the user explicitly wants the full local validation pipeline, because it may format or fix files.
4. Report results.
   - State whether the feature looks correct.
   - Call out failing tests, regressions, missing coverage, or assumptions that still need confirmation.
   - Mention the exact commands you ran.
5. Do not change code unless the user explicitly asks for fixes.
