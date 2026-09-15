"""Detect a coding agent driving the CLI, and identify the CLI to the platform.

Coding agents run the `softmax` and `coworld` CLIs as subprocesses and leave an environment
variable behind (Claude Code sets `CLAUDECODE=1` in every subprocess; others leak a session or
sandbox marker). Two things depend on knowing:

- The `User-Agent` header. Both CLIs used to arrive at the platform as httpx's default
  `python-httpx/<version>`, indistinguishable from any other script, so nothing about agent
  traffic could be measured. Now every request says which CLI, which version, and which agent.
- Output shape. An agent cannot answer an interactive prompt or read a browser, and on a usage
  error it needs the full help text, not a one-line "Try --help", to correct itself.

The marker list mirrors what GitHub's and Stripe's CLIs check. Order matters only for the
name reported when several markers are present (a Claude Code subagent inside Cursor is still
Claude Code).
"""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version

# (reported name, environment variable). Presence with a non-empty value is the signal.
AGENT_ENV_MARKERS: tuple[tuple[str, str], ...] = (
    ("claude-code", "CLAUDECODE"),
    ("claude-code", "CLAUDE_CODE_CHILD_SESSION"),
    ("claude-code", "CLAUDE_CODE_ENTRYPOINT"),
    ("codex", "CODEX_SANDBOX"),
    ("codex", "CODEX_THREAD_ID"),
    ("codex", "CODEX_CI"),
    ("cursor", "CURSOR_AGENT"),
    ("cursor", "CURSOR_TRACE_ID"),
    ("gemini-cli", "GEMINI_CLI"),
    ("copilot", "COPILOT_CLI"),
    ("opencode", "OPENCODE"),
    ("antigravity", "ANTIGRAVITY_AGENT"),
    ("augment", "AUGMENT_AGENT"),
    ("agent", "AI_AGENT"),
)


def detect_coding_agent(environ: dict[str, str] | os._Environ[str] = os.environ) -> str | None:
    """The coding agent driving this process, or None when a human (or plain script) is."""
    for name, variable in AGENT_ENV_MARKERS:
        if environ.get(variable):
            return name
    return None


def user_agent(distribution: str) -> str:
    """`<package>/<version> (<agent>)` for the User-Agent header of every platform request.

    `distribution` is the installed package (`coworld`, `softmax-cli`) whose name and version go
    on the wire. The agent suffix is present only under an agent.

    Source-tree execution (Bazel tests, a checkout on `sys.path`) has no distribution metadata,
    so the version reads `dev` there; an installed wheel always has it.
    """
    try:
        product_version = version(distribution)
    except PackageNotFoundError:
        product_version = "dev"
    agent = detect_coding_agent()
    if agent is None:
        return f"{distribution}/{product_version}"
    return f"{distribution}/{product_version} ({agent})"
