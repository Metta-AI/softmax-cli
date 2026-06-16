# AGENTS.md — softmax-cli

The `softmax` CLI: authentication and account tools for Softmax/Observatory. Other packages (e.g. `coworld`) depend on
it for login/token handling and pin an exact version. Deps: `typer`, `rich`, `httpx`, plus `fastapi`/`uvicorn` for the
local browser-login callback server. Published to PyPI.

## CLI

Installs a `softmax` entrypoint (`softmax.cli:app`, Typer):

```bash
uv run softmax login          # browser-based login (spins up a local callback server)
uv run softmax logout
uv run softmax status
uv run softmax get-login-url
uv run softmax get-token / set-token
uv run softmax player list / use <player-id> / unset
```

`softmax player use <player-id>` mints (or reuses) a 24h player session and stores it as the active player in
`~/.softmax/credentials.yaml` (`player_sessions`). Every auth-backed command in any CLI built on softmax-cli
(including `coworld`, which mounts this subapp as `coworld player`) then acts as that player, because they all
resolve their token through `softmax.auth.load_current_token`. `softmax player unset` clears the active pointer,
reverting to your main user credential. `player list`/`use` themselves authenticate with the user token (player
routes reject player-scoped tokens).

## Tests

```bash
uv run metta pytest packages/softmax-cli/tests -v
uv run metta pytest --changed
```

Tests cover auth/login, the Python API, player identity switching, and CLI plugin wiring; a `BUILD.bazel` exists under
`tests/`.

## Lint

```bash
./bazel/fix_lint.sh              # ruff (also runs via the Edit/Write hook)
```

## Source layout (`src/softmax/`)

- `cli.py` — the Typer app; mounts the `player` subapp via `add_typer`.
- `auth.py` — token storage, browser login URL, and `whoami` HTTP helpers.
- `players.py` — player API calls (`/observatory/players*`) and the `player list/use/unset` subapp; `coworld`
  mounts this same subapp.
- `perform_login.py` — the local FastAPI/uvicorn callback server used during `softmax login`.
- `_console.py` — shared rich console helpers.

## Gotchas

- Versioned via `setuptools_scm` off `softmax-v*` git tags (`fallback_version = 0.0.0`).
- Downstream packages pin an exact `softmax-cli==X.Y.Z`; bumping the public auth API can break them — coordinate version
  bumps with consumers like `coworld`.
- `player_sessions[server]` in `credentials.yaml` is a structured object (`active` pointer + per-player `cache` of
  `{token, expires_at}`), not a flat token string. Use the typed helpers in `auth.py`
  (`set_active_player_session`, `clear_active_player_session`, `get_active_player_id`, `get_cached_player_session`,
  `load_player_session`); `load_current_token` returns the active player token when one is selected, else the user
  token. `softmax player use/unset` drives this.
