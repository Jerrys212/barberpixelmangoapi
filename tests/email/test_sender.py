import io
import sys
from email.message import EmailMessage
from typing import Any

import aiosmtplib
import pytest
from pydantic import SecretStr, ValidationError

from src.email.config import EmailSettings
from src.email.sender import ConsoleEmailSender, OutgoingEmail, SmtpEmailSender

EMAIL = OutgoingEmail(to="cliente@example.com", subject="Asunto", body="Tu código es: 123456")


class TestConsoleEmailSender:
    async def test_prints_email_without_network(self, capsys: pytest.CaptureFixture[str]) -> None:
        await ConsoleEmailSender().send(EMAIL)

        output = capsys.readouterr().out
        assert "cliente@example.com" in output
        assert "123456" in output

    async def test_does_not_fail_on_console_that_cannot_encode_the_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        buffer = io.BytesIO()
        monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(buffer, encoding="cp1252"))
        email = OutgoingEmail(to="a@example.com", subject="Hola 💈", body="código 654321 ✂️")

        await ConsoleEmailSender().send(email)

        assert b"654321" in buffer.getvalue()


class TestSmtpEmailSender:
    async def test_sends_with_starttls_on_configured_port(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[EmailMessage, dict[str, Any]]] = []

        async def fake_send(message: EmailMessage, **kwargs: Any) -> None:
            calls.append((message, kwargs))

        monkeypatch.setattr(aiosmtplib, "send", fake_send)
        sender = SmtpEmailSender(
            host="smtp-relay.brevo.com",
            port=587,
            username="usuario",
            password=SecretStr("secreto"),
            sender="Barber <no-reply@example.com>",
            timeout=5,
        )

        await sender.send(EMAIL)

        message, kwargs = calls[0]
        assert kwargs["start_tls"] is True
        assert kwargs["port"] == 587
        assert kwargs["password"] == "secreto"
        assert message["To"] == "cliente@example.com"
        assert message["From"] == "Barber <no-reply@example.com>"

    async def test_swallows_smtp_errors_without_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def failing_send(message: EmailMessage, **kwargs: Any) -> None:
            raise aiosmtplib.SMTPException("caído")

        monkeypatch.setattr(aiosmtplib, "send", failing_send)
        sender = SmtpEmailSender("h", 587, "u", SecretStr("p"), "f@example.com", 5)

        await sender.send(EMAIL)


class TestEmailSettings:
    def test_smtp_backend_requires_credentials(self) -> None:
        with pytest.raises(ValidationError):
            EmailSettings(_env_file=None, email_backend="smtp", smtp_host="h")

    def test_console_backend_needs_no_credentials(self) -> None:
        settings = EmailSettings(_env_file=None, email_backend="console")

        assert settings.smtp_host is None
