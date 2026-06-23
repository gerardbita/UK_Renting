import json

from rentwatch.config import interpolate_env, load_config


def test_interpolate_env_resolves_known_vars(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    data = {"notifications": {"telegram": {"bot_token": "${TELEGRAM_BOT_TOKEN}"}}}
    resolved = interpolate_env(data)
    assert resolved["notifications"]["telegram"]["bot_token"] == "secret-token"


def test_interpolate_env_leaves_unknown_vars_untouched(monkeypatch):
    monkeypatch.delenv("DOES_NOT_EXIST", raising=False)
    assert interpolate_env("${DOES_NOT_EXIST}") == "${DOES_NOT_EXIST}"


def test_load_config_reads_token_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env-token")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "notifications": {
                    "telegram": {
                        "enabled": True,
                        "bot_token": "${TELEGRAM_BOT_TOKEN}",
                        "chat_id": "1",
                        "digest": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    config = load_config(config_path)
    assert config.notifications.telegram.bot_token == "env-token"
    assert config.notifications.telegram.digest is True
