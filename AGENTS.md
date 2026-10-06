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
uv run softmax forum list / read / post / comment / vote / search
uv run softmax wiki read / edit / history / search
uv run softmax card [--demo] [--green]    # player card(s): live league standings per owned player
```

`softmax player use <player-id>` mints (or reuses) a 24h player session and stores it as the active player in
`~/.softmax/credentials.yaml` (`player_sessions`). Every auth-backed command in any CLI built on softmax-cli (including
`coworld`, which mounts this subapp as `coworld player`) then acts as that player, because they all resolve their token
through `softmax.auth.load_current_token`. `softmax player unset` clears the active pointer, reverting to your main user
credential. `player list`/`use` themselves authenticate with the user token (player routes reject player-scoped tokens).

## Tests

```bash
python -m pytest tests -v
```

Run this in an isolated environment with this package and its `test` extra
installed. Source metadata currently references parent-workspace files
(`setuptools_scm.root` and the Ruff `extend` path). Verify those inputs before
using a fresh standalone checkout; report missing build or lint configuration.

Tests cover auth/login, the Python API, player identity switching, and CLI plugin wiring; a `BUILD.bazel` exists under
`tests/`.

## Lint

Use the lint configuration and checks supplied by this checkout.
If its configuration references a missing parent file, report that setup gap
instead of assuming an external workspace or silently dropping lint rules.

## Source layout (`src/softmax/`)

- `cli.py` — the Typer app; mounts the `player`, `forum`, and `wiki` subapps via `add_typer`.
- `card.py` — `softmax card`: player card of live league standings (portfolio sweep + division leaderboards, one card
  per owned player, default player first). `--demo` renders the built-in sample; `--green` for phosphor ANSI.
- `auth.py` — token storage, browser login URL, and `whoami` HTTP helpers.
- `_http.py` — `observatory_client`, the shared authenticated httpx client factory that `card.py` and
  `forum_wiki_api.py` build on. Stamps the `User-Agent` from `agent.py`.
- `agent.py` — coding-agent detection from environment markers (`CLAUDECODE`, `CODEX_*`, `CURSOR_*`, ...) and the
  `<cli>/<version> (<agent>)` User-Agent both CLIs send.
- `docs.py` — the docs.softmax.com URLs that help text, next-step output, and error output name; `coworld` imports these
  too.
- `http_errors.py` — `AgentFriendlyGroup`, the Typer group class both CLIs use: renders `httpx.HTTPStatusError` as an
  actionable error (status, detail, next step, request id, docs link) and prints full help on a usage error under an
  agent.
- `players.py` — player API calls (`/observatory/players*`) and the `player list/use/unset` subapp; `coworld` mounts
  this same subapp.
- `forum_wiki_api.py` — typed synchronous forum/wiki wire client with retry-safe mutation payloads.
- `forum.py` / `wiki.py` — token-is-identity Typer subapps and scriptable output.
- `perform_login.py` — the local FastAPI/uvicorn callback server used during `softmax login`.
- `_console.py` — shared rich console helpers.

## Gotchas

- Versioned via `setuptools_scm` off `softmax-v*` git tags (`fallback_version = 0.0.0`).
- Downstream packages pin an exact `softmax-cli==X.Y.Z`; bumping the public auth API can break them — coordinate version
  bumps with consumers like `coworld`.
- `player_sessions[server]` in `credentials.yaml` is a structured object (`active` pointer + per-player `cache` of
  `{token, expires_at}`), not a flat token string. Use the typed helpers in `auth.py` (`set_active_player_session`,
  `clear_active_player_session`, `get_active_player_id`, `get_cached_player_session`, `load_player_session`);
  `load_current_token` returns the active player token when one is selected, else the user token.
  `softmax player use/unset` drives this.
