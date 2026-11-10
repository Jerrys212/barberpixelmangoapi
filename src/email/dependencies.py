from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from src.email.config import EmailBackend, get_email_settings
from src.email.sender import ConsoleEmailSender, EmailSender, SmtpEmailSender


@lru_cache
def get_email_sender() -> EmailSender:
    settings = get_email_settings()
    if settings.email_backend == EmailBackend.CONSOLE:
        return ConsoleEmailSender()
    if not (
        settings.smtp_host and settings.smtp_user and settings.smtp_pass and settings.smtp_from
    ):
        raise RuntimeError("Configuración SMTP incompleta")
    return SmtpEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_pass,
        sender=settings.smtp_from,
        timeout=settings.smtp_timeout_seconds,
    )


EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]
