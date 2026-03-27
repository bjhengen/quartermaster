"""Tests for email configuration models."""

from quartermaster.core.config import EmailAccountConfig, EmailConfig, QuartermasterConfig


def test_email_account_config() -> None:
    account = EmailAccountConfig(
        provider="gmail",
        credential_file="credentials/gmail_personal.json",
        label="Personal Gmail",
    )
    assert account.provider == "gmail"
    assert account.credential_file == "credentials/gmail_personal.json"
    assert account.label == "Personal Gmail"


def test_email_config_defaults() -> None:
    config = EmailConfig()
    assert config.accounts == {}


def test_email_config_with_accounts() -> None:
    config = EmailConfig(
        accounts={
            "personal": EmailAccountConfig(
                provider="gmail",
                credential_file="credentials/gmail_personal.json",
                label="Personal Gmail",
            ),
            "fr": EmailAccountConfig(
                provider="gmail",
                credential_file="credentials/gmail_fr.json",
                label="Friendly Robots",
            ),
        }
    )
    assert len(config.accounts) == 2
    assert config.accounts["personal"].label == "Personal Gmail"
    assert config.accounts["fr"].provider == "gmail"


def test_quartermaster_config_has_email() -> None:
    config = QuartermasterConfig()
    assert hasattr(config, "email")
    assert config.email.accounts == {}
