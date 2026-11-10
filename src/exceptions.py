from typing import ClassVar

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded


class AppError(Exception):
    status_code: ClassVar[int] = status.HTTP_400_BAD_REQUEST
    code: ClassVar[str] = "APP_ERROR"
    message: ClassVar[str] = "Error en la solicitud"
    # Side effects (failed attempt counters, revocations) must survive the error response.
    commit_on_error: ClassVar[bool] = False

    def __init__(self, message: str | None = None, headers: dict[str, str] | None = None) -> None:
        self.detail = message or self.message
        self.headers = headers
        super().__init__(self.detail)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "detail": exc.detail},
            headers=exc.headers,
        )

    @app.exception_handler(RateLimitExceeded)
    async def handle_rate_limit(_: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"code": "RATE_LIMITED", "detail": "Demasiadas solicitudes, intenta más tarde"},
        )
