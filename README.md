# softmax-cli

The `softmax` command-line tool: authentication and account management for Softmax / Observatory. It provides
browser-based login (with a local callback server), token storage, account status, and player identity switching.
Other packages — notably `coworld` — depend on it for auth.

## Install

```bash
uv tool install softmax-cli
```

Within the metta workspace it is available via `uv sync`.

## Usage

```bash
uv run softmax login           # log in via the browser
uv run softmax status          # show current auth status
uv run softmax logout
uv run softmax get-token       # print the stored token
uv run softmax set-token       # store a token manually
uv run softmax player list     # list your players (active one highlighted)
uv run softmax player use ply_...  # act as a player in all auth-backed commands
uv run softmax player unset    # revert to your main user credential
```

## Development

```bash
uv run metta pytest packages/softmax-cli/tests -v   # run tests
uv run metta lint --fix                              # lint/format
```

See [AGENTS.md](AGENTS.md) for the source layout and versioning/compatibility notes.
