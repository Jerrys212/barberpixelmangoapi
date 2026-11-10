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

## Calidad

```bash
uv run ruff check --fix . && uv run ruff format .
uv run mypy src
uv run pytest -x -q
```

Ver `AGENTS.md` para convenciones de arquitectura, auth y flujo de Git.
