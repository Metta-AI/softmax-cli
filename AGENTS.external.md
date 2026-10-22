# Softmax CLI

This repository contains the public `softmax-cli` distribution and `softmax` command. Portable authentication,
credentials and HTTP clients belong to the `softmax-client` dependency.

Use Python 3.11 or 3.12. Install development dependencies with `uv sync --extra test`, then run `uv run pytest tests`.
Run `uv run softmax --help` and `uv run softmax get-login-url` to inspect the command surface.

Use an isolated `SOFTMAX_CONFIG_DIR` for authentication changes. Preserve saved credential data and keep tokens out of
logs. Commands requiring user authority must select the user token, while token-is-identity commands honor an active
player. Follow the supported Typer/Click range in `pyproject.toml`.

Write only complete E2E or system workflow coverage. Existing suites remain usable. Public package releases use the
`softmax-v*` tag stream and require the matching portable client release first.
