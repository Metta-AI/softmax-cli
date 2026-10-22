import pytest

from softmax_client.credentials import CONFIG_DIR_ENV


@pytest.fixture(autouse=True)
def _ignore_config_dir_override(monkeypatch: pytest.MonkeyPatch) -> None:
    # Tests sandbox credentials by pointing HOME at tmp_path. An inherited
    # SOFTMAX_CONFIG_DIR would bypass that and write to the caller's real
    # credentials, so drop it; tests that exercise the override set it back.
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
