"""Coding-agent detection and installed distribution attribution."""

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
    """Identify the calling distribution and agent; source-only execution uses version `dev`."""
    try:
        product_version = version(distribution)
    except PackageNotFoundError:
        product_version = "dev"
    agent = detect_coding_agent()
    if agent is None:
        return f"{distribution}/{product_version}"
    return f"{distribution}/{product_version} ({agent})"
