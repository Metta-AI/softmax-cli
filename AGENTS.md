# AGENTS.md — softmax-cli

The `softmax` CLI: authentication and account tools for Softmax/Observatory. Other packages (e.g. `coworld`) depend on
it for login/token handling and pin an exact version. Deps: `typer`, `rich`, `httpx`, plus `fastapi`/`uvicorn` for the
local browser-login callback server. The `cogames` optional extra mounts the cogames CLI as a `softmax cogames`
subcommand. Published to PyPI.

## CLI

Installs a `softmax` entrypoint (`softmax.cli:app`, Typer):

```bash
uv run softmax login          # browser-based login (spins up a local callback server)
uv run softmax logout
uv run softmax status
uv run softmax get-login-url
uv run softmax get-token / set-token
uv run softmax cogames ...    # only when installed with the `cogames` extra
```

## Tests

```bash
uv run metta pytest packages/softmax-cli/tests -v
uv run metta pytest --changed
```

Tests cover auth/login, the Python API, and CLI plugin wiring; a `BUILD.bazel` exists under `tests/`.

## Lint

```bash
uv run metta lint --fix              # ruff (also runs via the Edit/Write hook)
```

## Source layout (`src/softmax/`)

- `cli.py` — the Typer app; mounts the optional `cogames` subapp via `add_typer`.
- `auth.py` — auth/session state and token validation.
- `perform_login.py` — the local FastAPI/uvicorn callback server used during `softmax login`.
- `token_storage.py` — on-disk token persistence.
- `cogames.py` — the optional cogames subcommand wiring.
- `_console.py` — shared rich console helpers.

## Gotchas

- Versioned via `setuptools_scm` off `softmax-v*` git tags (`fallback_version = 0.0.0`).
- Downstream packages pin an exact `softmax-cli==X.Y.Z`; bumping the public auth API can break them — coordinate version
  bumps with consumers like `coworld`.
