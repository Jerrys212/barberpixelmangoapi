from fastapi import status

from src.exceptions import AppError

_BEARER = {"WWW-Authenticate": "Bearer"}


class InvalidCredentials(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "INVALID_CREDENTIALS"
    message = "Credenciales inválidas"
    commit_on_error = True

    def __init__(self) -> None:
        super().__init__(headers=_BEARER)


class NotAuthenticated(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "NOT_AUTHENTICATED"
    message = "No autenticado"

    def __init__(self) -> None:
        super().__init__(headers=_BEARER)


class InvalidToken(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "INVALID_TOKEN"
    message = "Token inválido o expirado"

    def __init__(self) -> None:
        super().__init__(headers=_BEARER)


class SessionRevoked(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "SESSION_REVOKED"
    message = "La sesión fue revocada o expiró"
    commit_on_error = True

    def __init__(self) -> None:
        super().__init__(headers=_BEARER)


class Forbidden(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"
    message = "No tienes permiso para esta operación"


class EmailNotVerified(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "EMAIL_NOT_VERIFIED"
    message = "Debes verificar tu correo para continuar"


class OtpInvalid(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "OTP_INVALID"
    message = "Código inválido o expirado"
    commit_on_error = True


class SessionNotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "SESSION_NOT_FOUND"
    message = "Sesión no encontrada"
