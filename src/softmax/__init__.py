from __future__ import annotations

import importlib
import sys
from pkgutil import extend_path

from softmax.auth import DEFAULT_API_SERVER, load_user_token
from softmax.perform_login import do_interactive_login_for_token

__path__ = extend_path(__path__, __name__)


def login(
    *,
    api_server: str = DEFAULT_API_SERVER,
    force: bool = False,
    open_browser: bool = True,
) -> str:
    token = None if force else load_user_token(server=api_server)
    if token is not None:
        return token

    if not sys.stdin.isatty():
        raise RuntimeError(
            "No saved Softmax token found and interactive login requires a TTY. "
            "Run `softmax login` or `softmax set-token` first."
        )

    do_interactive_login_for_token(
        api_server=api_server,
        agent_hint=(
            "If you are a coding agent, ask your human to open the URL below and give you "
            "the auth code. Then paste the code into this window or run:\n"
            "\n"
            "softmax exchange-code '<CODE>'"
        ),
        open_browser=open_browser,
    )

    token = load_user_token(server=api_server)
    if token is None:
        raise RuntimeError(f"Interactive login did not save a token for {api_server}")
    return token


def __getattr__(name: str) -> object:
    if name == "cogames":
        return importlib.import_module("softmax.cogames")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["login", "cogames"]
