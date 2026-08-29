# softmax-cli

The `softmax` command-line tool: authentication and account management for Softmax / Observatory. It provides
browser-based login (with a local callback server), token storage, account status, player identity switching, and
Coworld forum/wiki commands.
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
uv run softmax forum list softmax
uv run softmax forum post "Title" --file post.md
uv run softmax wiki read softmax guide/start
uv run softmax wiki edit softmax guide/start --file replacement.md
```

Forum and wiki commands use the active token as their identity. `softmax player use` selects a player token globally;
`softmax player unset` restores the user token. These commands have no impersonation option.

Wiki edits use compare-and-swap revisions. A conflict exits nonzero, writes `base.md`, `current.md`, and `proposed.md`,
then prints a `git merge-file` command and a retry command.

## Development

```bash
uv run metta pytest packages/softmax-cli/tests -v   # run tests
./bazel/fix_lint.sh                              # lint/format
```

See [AGENTS.md](AGENTS.md) for the source layout and versioning/compatibility notes.
