from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.auth.router import router as auth_router
from src.availability.router import router as availability_router
from src.business.router import router as business_router
from src.catalog.router import router as catalog_router
from src.config import Environment, get_settings
from src.database import engine
from src.email.config import EmailBackend, get_email_settings
from src.exceptions import register_exception_handlers
from src.health.router import router as health_router
from src.rate_limit import limiter
from src.schedule.router import router as schedule_router
from src.users.router import router as users_router

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    if (
        settings.environment == Environment.PRODUCTION
        and get_email_settings().email_backend == EmailBackend.CONSOLE
    ):
        raise RuntimeError("EMAIL_BACKEND=console no está permitido en producción")

    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.limiter = limiter
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(health_router)
    for router in (
        auth_router,
        users_router,
        business_router,
        catalog_router,
        schedule_router,
        availability_router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    return app


app = create_app()
