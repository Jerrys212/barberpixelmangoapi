# BarberPixelMango API

API REST con FastAPI + PostgreSQL (SQLAlchemy async, Alembic).

## Requisitos

- Python 3.14 y [uv](https://docs.astral.sh/uv/)
- PostgreSQL con dos bases: la de desarrollo y la de tests

## Puesta en marcha

```bash
uv sync
cp .env.example .env          # ajusta DATABASE_URL y TEST_DATABASE_URL
uv run alembic upgrade head
uv run fastapi dev src/main.py
```

- Health check: `GET http://localhost:8000/health`
- Docs: `http://localhost:8000/docs` (desactivadas con `ENVIRONMENT=production`)
- API: todas las rutas bajo `/api/v1` (`/auth/*`, `/users/me`, `/business`, `/services`,
  `/schedule/*`, `/availability`).
- Con `EMAIL_BACKEND=console` los correos (y sus códigos OTP) se imprimen en la consola del
  servidor; con `EMAIL_BACKEND=smtp` se envían por SMTP con las variables `SMTP_*`.

## Cuenta del dueño

La cuenta `OWNER` solo se crea y recupera desde consola (la contraseña se pide de forma
interactiva):

```bash
uv run python -m src.auth.cli create-owner --email dueno@example.com --name "Nombre" --phone 5512345678
uv run python -m src.auth.cli reset-owner-password
```

## Calidad

```bash
uv run ruff check --fix . && uv run ruff format .
uv run mypy src
uv run pytest -x -q
```

Ver `AGENTS.md` para convenciones de arquitectura, auth y flujo de Git.
