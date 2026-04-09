from __future__ import annotations

import importlib
import sys
from pkgutil import extend_path

from softmax.auth import DEFAULT_COGAMES_SERVER, load_token
from softmax.perform_login import do_interactive_login_for_token
from softmax.token_storage import TokenKind

__path__ = extend_path(__path__, __name__)


def login(
    *,
    login_server: str = DEFAULT_COGAMES_SERVER,
    force: bool = False,
    open_browser: bool = True,
) -> str:
    token = load_token(token_kind=TokenKind.COGAMES, server=login_server)
    if token is not None and not force:
        return token

    if not sys.stdin.isatty():
        raise RuntimeError(
            "No saved Softmax token found and interactive login requires a TTY. "
            "Run `softmax login` or `softmax set-token` first."
        )

    do_interactive_login_for_token(
        login_server=login_server,
        server_to_save_token_under=login_server,
        token_kind=TokenKind.COGAMES,
        agent_hint=(
            "If you are a coding agent, ask your human to open the URL below and give you "
            "the auth token. Then paste the token into this window or run:\n"
            "\n"
            "softmax set-token '<TOKEN>'"
        ),
        open_browser=open_browser,
    )

    token = load_token(token_kind=TokenKind.COGAMES, server=login_server)
    if token is None:
        raise RuntimeError(f"Interactive login did not save a token for {login_server}")
    return token


def __getattr__(name: str) -> object:
    if name == "cogames":
        return importlib.import_module("softmax.cogames")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["login", "cogames"]
