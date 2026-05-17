# Local .venv Activation Rule

It is **CRITICAL** that the local `.venv` is activated before executing any command in this project.

Most tools, scripts, and workflows in this repository depend on the correct Python environment, and important code such as `./run-tests.sh` will fail or produce inconsistent results without it.

- You MUST activate the local `.venv` before running any commands, tests, or scripts, including but not limited to `./run-tests.sh`, CLI invocations, and automation tasks.
- Activating the `.venv` ensures all dependencies, correct Python version (3.11), and environment variables are present and used for the session.
- Do not run project scripts using the system Python or a globally installed Python interpreter.

**To activate the local environment:**

On macOS/Linux:
```bash
source .venv/bin/activate
```
On Windows:
```cmd
.venv\Scripts\activate
```

- Running without the `.venv` activated may lead to missing dependencies, wrong Python version, or failures in core CLI and testing commands.
- If you see errors related to module imports, pip/uv/pytest/ruff not found, or Python version mismatch, double-check your environment.

**Summary:**
> Always `activate` the `.venv` before you do anything in this project.
