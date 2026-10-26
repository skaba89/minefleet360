"""Transport email : aucune connexion ni donnée personnelle réelle."""

import json
import logging
import os
import smtplib
import stat
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.email import EmailMessage, FileCaptureEmailSender, SMTPEmailSender, build_email_sender

MESSAGE = EmailMessage(
    to="recipient-fictif@example.com",
    subject="Invitation fictive",
    body="https://fleet.example.com/#token=synthetic-token-only",
    kind="INVITATION",
)


def _settings(**changes: object) -> Settings:
    values: dict[str, object] = {
        "env": "test",
        "mail_backend": "smtp",
        "mail_capture_dir": "var/mail",
        "mail_capture_ttl_seconds": 86400,
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "smtp-fictif",
        "smtp_password": SecretStr("synthetic-smtp-password"),
        "smtp_sender": "MINEFLEET Fictif <noreply@example.com>",
        "smtp_use_ssl": False,
        "smtp_timeout_seconds": 10,
        "public_web_url": "https://fleet.example.com",
    }
    values.update(changes)
    return cast(Settings, SimpleNamespace(**values))


def test_capture_permissions_purge_and_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    directory = tmp_path / "mail"
    directory.mkdir(mode=0o777)
    old = directory / f"{uuid.uuid4()}.json"
    old.write_text("expired fictitious capture", encoding="utf-8")
    os.utime(old, (time.time() - 3600, time.time() - 3600))
    unrelated = directory / "notes.json"
    unrelated.write_text("keep", encoding="utf-8")
    os.utime(unrelated, (time.time() - 3600, time.time() - 3600))
    outside = tmp_path / "outside.json"
    outside.write_text("keep outside", encoding="utf-8")
    symlink = directory / f"{uuid.uuid4()}.json"
    symlink.symlink_to(outside)

    with caplog.at_level(logging.INFO, logger="minefleet.email"):
        FileCaptureEmailSender(str(directory), ttl_seconds=60).send(MESSAGE)

    assert not old.exists() and unrelated.exists() and symlink.is_symlink() and outside.exists()
    captures = [
        path for path in directory.glob("*.json") if path.name != "notes.json" and not path.is_symlink()
    ]
    assert len(captures) == 1
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(captures[0].stat().st_mode) == 0o600
    assert json.loads(captures[0].read_text(encoding="utf-8"))["to"] == MESSAGE.to
    assert MESSAGE.to not in caplog.text and "synthetic-token-only" not in caplog.text


def test_capture_refuses_symlink_directory(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(OSError):
        FileCaptureEmailSender(str(link)).send(MESSAGE)
    assert list(target.iterdir()) == []


def test_capture_refuses_symlink_parent(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(OSError):
        FileCaptureEmailSender(str(link / "mail")).send(MESSAGE)
    assert list(target.iterdir()) == []


@pytest.mark.parametrize("use_ssl", [False, True])
def test_smtp_requires_tls_before_auth_and_send(
    monkeypatch: pytest.MonkeyPatch, use_ssl: bool, caplog: pytest.LogCaptureFixture
) -> None:
    factory = MagicMock()
    other_factory = MagicMock()
    smtp = factory.return_value.__enter__.return_value
    monkeypatch.setattr(
        "app.core.email.smtplib.SMTP_SSL" if use_ssl else "app.core.email.smtplib.SMTP", factory
    )
    monkeypatch.setattr(
        "app.core.email.smtplib.SMTP" if use_ssl else "app.core.email.smtplib.SMTP_SSL", other_factory
    )
    sender = build_email_sender(_settings(smtp_use_ssl=use_ssl))
    factory.assert_not_called()  # validation de configuration uniquement, aucun envoi au démarrage
    assert isinstance(sender, SMTPEmailSender)
    with caplog.at_level(logging.INFO, logger="minefleet.email"):
        sender.send(MESSAGE)

    other_factory.assert_not_called()
    assert factory.call_args.kwargs["timeout"] == 10
    if use_ssl:
        assert factory.call_args.kwargs["context"].check_hostname is True
        smtp.starttls.assert_not_called()
    else:
        assert smtp.starttls.call_args.kwargs["context"].check_hostname is True
        assert [call[0] for call in smtp.method_calls] == [
            "ehlo",
            "starttls",
            "ehlo",
            "login",
            "send_message",
        ]
    smtp.login.assert_called_once_with("smtp-fictif", "synthetic-smtp-password")
    sent = smtp.send_message.call_args.args[0]
    assert sent["To"] == MESSAGE.to and MESSAGE.body in sent.get_content()
    assert MESSAGE.to not in caplog.text and "synthetic-token-only" not in caplog.text


def test_smtp_failure_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = MagicMock()
    factory.return_value.__enter__.return_value.send_message.side_effect = OSError(MESSAGE.to)
    monkeypatch.setattr("app.core.email.smtplib.SMTP", factory)
    with pytest.raises(RuntimeError, match="Échec du transport email") as exc:
        build_email_sender(_settings()).send(MESSAGE)
    assert MESSAGE.to not in str(exc.value) and exc.value.__suppress_context__ is True


def test_smtp_never_falls_back_to_plaintext(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = MagicMock()
    smtp = factory.return_value.__enter__.return_value
    smtp.starttls.side_effect = smtplib.SMTPNotSupportedError("TLS unavailable")
    monkeypatch.setattr("app.core.email.smtplib.SMTP", factory)
    with pytest.raises(RuntimeError, match="Échec du transport email"):
        build_email_sender(_settings()).send(MESSAGE)
    smtp.login.assert_not_called()
    smtp.send_message.assert_not_called()


def test_smtp_supports_relay_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = MagicMock()
    smtp = factory.return_value.__enter__.return_value
    monkeypatch.setattr("app.core.email.smtplib.SMTP", factory)
    build_email_sender(_settings(smtp_username="", smtp_password=None)).send(MESSAGE)
    smtp.starttls.assert_called_once()
    smtp.login.assert_not_called()
    smtp.send_message.assert_called_once()


@pytest.mark.parametrize(
    "changes",
    [
        {"env": "production", "mail_backend": "capture"},
        {"smtp_host": ""},
        {"smtp_sender": ""},
        {"smtp_sender": "bad\r\n@example.com"},
        {"smtp_username": "", "smtp_password": SecretStr("synthetic-password")},
        {"smtp_username": "user", "smtp_password": None},
        {"env": "staging", "public_web_url": "http://fleet.example.com"},
        {"env": "production", "public_web_url": "http://fleet.example.com"},
    ],
)
def test_email_configuration_fails_closed(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        build_email_sender(_settings(**changes))


def test_capture_allowed_in_development(tmp_path: Path) -> None:
    sender = build_email_sender(_settings(mail_backend="capture", mail_capture_dir=str(tmp_path / "mail")))
    assert isinstance(sender, FileCaptureEmailSender)
