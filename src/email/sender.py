import logging
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib
from pydantic import SecretStr

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    async def send(self, email: OutgoingEmail) -> None: ...


class ConsoleEmailSender:
    async def send(self, email: OutgoingEmail) -> None:
        text = (
            f"\n--- EMAIL (console) ---\nTo: {email.to}\nSubject: {email.subject}\n\n"
            f"{email.body}\n-----------------------\n"
        )
        # Windows consoles default to cp1252; never let an unencodable char fail the request.
        encoding = sys.stdout.encoding or "utf-8"
        sys.stdout.write(text.encode(encoding, errors="replace").decode(encoding))
        sys.stdout.flush()


class SmtpEmailSender:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: SecretStr,
        sender: str,
        timeout: float,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._timeout = timeout

    async def send(self, email: OutgoingEmail) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = email.to
        message["Subject"] = email.subject
        message.set_content(email.body)
        try:
            await aiosmtplib.send(
                message,
                hostname=self._host,
                port=self._port,
                username=self._username,
                password=self._password.get_secret_value(),
                start_tls=True,
                timeout=self._timeout,
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            logger.error("Fallo al enviar correo por SMTP: %s", type(exc).__name__)
