# softmax-cli

The `softmax` command-line tool: authentication and account management for Softmax / Observatory. It provides
browser-based login (with a local callback server), token storage, and account status. Other packages — notably
`coworld` — depend on it for auth. Installing with the `cogames` extra mounts the cogames CLI as a `softmax cogames`
subcommand.

## Install

```bash
uv tool install softmax-cli            # standalone
uv tool install "softmax-cli[cogames]" # with the cogames subcommand
```

Within the metta workspace it is available via `uv sync`.

## Usage

```bash
uv run softmax login           # log in via the browser
uv run softmax status          # show current auth status
uv run softmax logout
uv run softmax get-token       # print the stored token
uv run softmax set-token       # store a token manually
uv run softmax cogames ...     # only with the `cogames` extra
```

## Development

```bash
uv run metta pytest packages/softmax-cli/tests -v   # run tests
uv run metta lint --fix                              # lint/format
```

See [AGENTS.md](AGENTS.md) for the source layout and versioning/compatibility notes.
