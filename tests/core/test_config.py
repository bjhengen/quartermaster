"""Tests for configuration loading."""

from pathlib import Path

import pytest

from quartermaster.core.config import (
    AnthropicConfig,
    DatabaseConfig,
    LocalLLMConfig,
    load_config,
)


def test_database_config_defaults() -> None:
    cfg = DatabaseConfig(dsn="localhost:1521/test", user="qm", password="pw")
    assert cfg.pool_min == 2
    assert cfg.pool_max == 10


def test_llm_config_defaults() -> None:
    local = LocalLLMConfig()
    assert local.base_url == "http://localhost:8200/v1"
    assert local.preferred_model == "qwen3.5-27b"
    assert local.timeout_seconds == 60


def test_anthropic_config_requires_key_file() -> None:
    cfg = AnthropicConfig(api_key_file="/path/to/key")
    assert cfg.default_model == "claude-sonnet-4-20250514"


def test_full_config_from_yaml(tmp_path: Path) -> None:
    yaml_content = """
quartermaster:
  telegram_bot_token: "test-token"
  allowed_user_ids:
    - 12345
  database:
    dsn: "localhost:1521/test_pdb"
    user: "qm"
    password: "testpw"
  llm:
    local:
      base_url: "http://localhost:8200/v1"
    anthropic:
      api_key_file: "/tmp/key"
    monthly_budget_usd: 50.0
  plugins_dir: "/app/plugins"
"""
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(yaml_content)
    cfg = load_config(config_file)
    assert cfg.telegram_bot_token == "test-token"
    assert cfg.allowed_user_ids == [12345]
    assert cfg.database.dsn == "localhost:1521/test_pdb"
    assert cfg.llm.monthly_budget_usd == 50.0


def test_load_config_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_config(Path("/nonexistent/settings.yaml"))
