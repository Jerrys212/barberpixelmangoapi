# AGENTS.md

API REST con FastAPI + PostgreSQL. Autenticación con access token (JWT, corta duración) y
refresh token (opaco, rotativo, guardado hasheado en BD).

Este archivo es la guía para agentes de IA (Claude Code, Codex, Cursor). Léelo completo antes
de escribir código. Las reglas marcadas como **NUNCA** / **SIEMPRE** no son negociables.

## Stack

| Pieza            | Elección                                                  |
| ---------------- | --------------------------------------------------------- |
| Python           | 3.12+                                                     |
| Paquetes         | `uv` (nunca `pip` directo)                                |
| Framework        | FastAPI (usa `Annotated[T, Depends(...)]`)                |
| Validación       | Pydantic v2 + `pydantic-settings`                         |
| BD               | PostgreSQL + SQLAlchemy 2.0 **async** + `asyncpg`         |
| Migraciones      | Alembic                                                   |
| JWT              | `PyJWT` (`import jwt`) — **NUNCA** `python-jose`          |
| Hash de password | `pwdlib[argon2]` — **NUNCA** `passlib` ni bcrypt manual   |
| Tests            | `pytest` + `httpx.AsyncClient` + `ASGITransport`, BD real |
| Calidad          | `ruff` (lint + formato), `mypy --strict`                  |

## Comandos

**SIEMPRE** antepón `uv run` a cualquier comando de Python.

```bash
uv sync                                              # instalar dependencias
docker compose up -d db                              # PostgreSQL local
uv run fastapi dev src/main.py                       # servidor de desarrollo
uv run pytest -x -q                                  # tests
uv run ruff check --fix . && uv run ruff format .    # lint + formato
uv run mypy src                                      # tipos
uv run alembic revision --autogenerate -m "descripcion"   # nueva migración
uv run alembic upgrade head                          # aplicar migraciones
```

**Definición de terminado:** una tarea NO está terminada hasta que `ruff`, `mypy` y `pytest`
pasan sin errores. No digas "listo" sin haberlos corrido.

## Estructura (modular por dominio)

```
src/
├── main.py            # crea la app, lifespan, registra routers y exception handlers
├── config.py          # Settings globales (pydantic-settings)
├── database.py        # engine async, sessionmaker, dependencia get_session
├── models.py          # Base declarativa con naming_convention + mixins (timestamps)
├── exceptions.py      # AppError base + handler global
├── auth/
│   ├── router.py      # /auth/login, /auth/refresh, /auth/logout
│   ├── schemas.py     # TokenPair, LoginRequest, RefreshRequest
│   ├── models.py      # RefreshToken
│   ├── repository.py  # queries de refresh tokens
│   ├── service.py     # login, rotación, revocación
│   ├── security.py    # crear/decodificar JWT, hash/verify password, generar refresh token
│   ├── dependencies.py# CurrentUser, require_active_user
│   ├── config.py      # AuthSettings (secret, expiraciones)
│   └── exceptions.py
└── users/
    ├── router.py
    ├── schemas.py
    ├── models.py
    ├── repository.py
    ├── service.py
    └── exceptions.py
tests/                 # espejo de src/: tests/auth/test_router.py, tests/users/test_service.py
alembic/
```

- Un dominio = una carpeta. Archivos nuevos van dentro del dominio, no en carpetas globales
  tipo `routers/` o `services/`.
- Imports entre dominios con nombre explícito:
  `from src.users import service as users_service`. **NUNCA** `import *`.
- Módulo de referencia para copiar patrones: `src/users/`.

## Capas y responsabilidades

Flujo en una sola dirección: **router → service → repository → BD**.

| Capa         | Hace                                                                                            | NO hace                                   |
| ------------ | ----------------------------------------------------------------------------------------------- | ----------------------------------------- |
| `router`     | Recibe request, inyecta dependencias, llama al service, define `response_model` y `status_code` | Lógica de negocio, queries SQL            |
| `service`    | Reglas de negocio, permisos, orquesta repositories                                              | Conocer HTTP (`Request`, `HTTPException`) |
| `repository` | **Todas** las queries SQLAlchemy                                                                | Reglas de negocio                         |
| `schemas`    | Contratos de entrada/salida (Pydantic)                                                          | Exponer modelos ORM directamente          |

```python
# src/users/router.py
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def read_me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(data: UserUpdate, user: CurrentUser, session: SessionDep) -> User:
    return await users_service.update(session, user, data)
```

```python
# src/users/service.py
async def update(session: AsyncSession, user: User, data: UserUpdate) -> User:
    repo = UserRepository(session)
    if data.email and await repo.get_by_email(data.email):
        raise EmailAlreadyRegistered()  # AppError con status 409
    return await repo.update(user, data.model_dump(exclude_unset=True))
```

## Base de datos

- Modelos con tipado SQLAlchemy 2.0: `Mapped[...]` y `mapped_column(...)`.
- PK: `UUID` (`uuid.uuid4`). Timestamps: `DateTime(timezone=True)`, siempre en UTC.
- `Base.metadata` usa `naming_convention` (pk/fk/ix/uq/ck) para que Alembic genere nombres estables.
- **Todas las relaciones con `lazy="raise"`.** Carga explícita con `selectinload` / `joinedload`.
  (Evita N+1 y el error `MissingGreenlet` en async.)
- `async_sessionmaker(..., expire_on_commit=False)`.
- Sesión por request vía la dependencia `get_session`: hace `commit` al final si no hubo error y
  `rollback` si lo hubo. **NUNCA** llames `session.commit()` en services ni repositories; usa
  `session.flush()` si necesitas el id generado antes de terminar.
- Migraciones:
  - Toda modificación de modelos lleva su migración de Alembic en el mismo cambio.
  - Revisa el archivo autogenerado antes de darlo por bueno (Alembic no detecta todo: renombres,
    cambios de tipo, enums).
  - Cada migración tiene `downgrade()` funcional.
  - **NUNCA** edites una migración que ya se aplicó en otro entorno; crea una nueva.
- **NUNCA** construyas SQL con f-strings o concatenación. Usa el ORM o `text()` con parámetros.

## Autenticación (access + refresh)

### Access token

- JWT firmado (HS256 con `AUTH_SECRET_KEY` de ≥32 bytes, o RS256 si hay varios servicios).
- Vida corta: **15 minutos** (`ACCESS_TOKEN_EXPIRE_MINUTES`).
- Claims: `sub` (user id), `exp`, `iat`, `jti`, `type="access"`.
- Al decodificar: **SIEMPRE** pasa `algorithms=[...]` explícito, valida `exp` y verifica
  `type == "access"`. Un refresh token **NUNCA** debe funcionar como access token.
- Se envía en `Authorization: Bearer <token>`.

### Refresh token

- **Opaco**, no JWT: `secrets.token_urlsafe(64)`.
- En BD se guarda **solo el hash** (SHA-256), nunca el valor en claro. Tabla `refresh_tokens`:
  `id, user_id, token_hash (unique), family_id, expires_at, revoked_at, replaced_by_id, created_at`.
- Vida: **7 días** (`REFRESH_TOKEN_EXPIRE_DAYS`).
- **Rotación obligatoria:** cada `POST /auth/refresh` revoca el token usado y emite un par nuevo
  (mismo `family_id`).
- **Detección de reuso:** si llega un refresh token ya revocado, revoca **toda su familia** y
  responde 401. (Es señal de robo.)
- `POST /auth/logout` revoca el refresh token actual. Cambiar password revoca todos los del usuario.

### Passwords y respuestas

- Hash con `pwdlib` (argon2). **NUNCA** guardes ni compares passwords en claro.
- Login fallido: mismo mensaje y mismo status (401 "Credenciales inválidas") exista o no el
  usuario. Incluye header `WWW-Authenticate: Bearer`.
- **NUNCA** loguees passwords, tokens, hashes ni el header `Authorization`.
- `CurrentUser = Annotated[User, Depends(get_current_user)]` en `auth/dependencies.py` es la
  única forma de obtener el usuario autenticado. Un endpoint sin esta dependencia es público:
  hazlo solo si es intencional.

## Errores

- Errores de negocio heredan de `AppError(message, status_code)` en `src/exceptions.py`; un
  handler global los convierte en JSON. Usa 404, 409, 403, 401 según corresponda.
- 422 queda **solo** para validación de payload (lo genera FastAPI/Pydantic).
- Los services lanzan `AppError`, no `HTTPException`.
- **NUNCA** `except Exception:` ni `except:` desnudo alrededor de lógica. Captura la excepción
  específica.

## Configuración y secretos

- Toda configuración vía `pydantic-settings` leyendo variables de entorno / `.env`.
- Settings por dominio (`AuthSettings` en `auth/config.py`), cacheados con `@lru_cache`.
- **NUNCA** hardcodees secretos, URLs de BD ni orígenes CORS. **NUNCA** commitees `.env`
  (sí `.env.example`).
- CORS: lista explícita de orígenes. **NUNCA** `allow_origins=["*"]` junto con `allow_credentials=True`.
- Docs (`/docs`, `/openapi.json`) desactivadas en producción.

## Async

| La ruta hace…                                    | Usa                                         |
| ------------------------------------------------ | ------------------------------------------- |
| I/O con cliente async (`await`)                  | `async def`                                 |
| Llamada a librería síncrona                      | `await run_in_threadpool(fn, ...)`          |
| Trabajo CPU pesado o tarea que debe reintentarse | Worker (Celery / Arq), no `BackgroundTasks` |

Dentro de `async def` **NUNCA**: `requests`, `time.sleep`, `open()` de archivos grandes, drivers
síncronos de BD. Usa `httpx.AsyncClient`, `asyncio.sleep`, `asyncpg`.

## Schemas (Pydantic)

- Convención de nombres: `XCreate`, `XUpdate` (todos los campos opcionales con `None`), `XOut`.
- Los schemas de salida usan `model_config = ConfigDict(from_attributes=True)`.
- `XOut` **NUNCA** incluye `hashed_password` ni datos internos.
- Usa validadores incluidos: `EmailStr`, `Field(min_length=..., max_length=...)`, enums.
- Pydantic v2 únicamente: `model_dump()`, `model_validate()`, `@field_validator`.
  **NUNCA** `.dict()`, `.from_orm()`, `class Config`, `json_encoders`.

## Tests

- Estructura espejo de `src/`. Una clase por función bajo prueba, un test por escenario.
- BD PostgreSQL real de pruebas (no SQLite, no mocks de BD). Cada test corre en una transacción
  que se revierte.
- Cliente: `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`.
- Sustituye servicios externos con `app.dependency_overrides`.
- Un fix de bug lleva un test de regresión que falla sin el fix.
- Tests de auth obligatorios: login ok / password incorrecto / usuario inexistente, token expirado,
  refresh usado como access (401), rotación de refresh, reuso de refresh revocado (revoca familia),
  logout, endpoint protegido sin token (401).

## Flujo para agregar un dominio o funcionalidad

1. Modelo en `src/{dominio}/models.py`
2. Migración: `uv run alembic revision --autogenerate -m "..."` y revisarla
3. Schemas en `schemas.py`
4. Queries en `repository.py`
5. Lógica en `service.py`
6. Endpoints en `router.py` y registrarlo en `main.py`
7. Tests en `tests/{dominio}/`
8. Correr ruff + mypy + pytest

## Anti-patrones (revisa tu diff contra esta lista)

| Anti-patrón                                     | Corrección                                 |
| ----------------------------------------------- | ------------------------------------------ |
| `requests` / `time.sleep` dentro de `async def` | `httpx.AsyncClient` / `asyncio.sleep`      |
| `from jose import jwt`                          | `import jwt` (PyJWT)                       |
| `passlib` / `CryptContext`                      | `pwdlib` con argon2                        |
| `jwt.decode(token, key)` sin `algorithms=`      | Siempre `algorithms=["HS256"]` explícito   |
| Refresh token como JWT sin guardar en BD        | Opaco + hash en BD + rotación              |
| Guardar el refresh token en claro               | Guardar SHA-256                            |
| `def f(x = Depends(...))`                       | `x: Annotated[T, Depends(...)]`            |
| Query SQLAlchemy dentro de router o service     | Moverla al repository                      |
| `session.commit()` en service/repository        | Lo hace `get_session` al final del request |
| Relación con lazy loading implícito             | `lazy="raise"` + `selectinload`            |
| `HTTPException` dentro de un service            | `AppError` del dominio                     |
| `except Exception: pass`                        | Capturar la excepción específica           |
| Devolver el modelo ORM sin `response_model`     | Definir `response_model=XOut`              |
| Pydantic v1 (`.dict()`, `class Config`)         | Pydantic v2                                |
| Modificar modelo sin migración                  | Generar y revisar migración                |
| Mockear la BD en tests de endpoints             | BD de pruebas real                         |

## Flujo de Git

### Ramas

- `main`: producción
- `dev`: desarrollo
- `feat/*`: funcionalidades nuevas
- `fix/*`: corrección de bugs
- `hotfix/*`: correcciones críticas en producción

### Commits

- Mensajes de commit en **inglés**
- Formato conventional commits (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `test:`)
- Describe el "por qué", no solo el "qué"

## Reglas generales

- No modifiques código que no tenga que ver con la tarea.
- No agregues dependencias nuevas sin decir por qué; usa `uv add`.
- Type hints en todas las funciones; el código debe pasar `mypy --strict`.
- Si una instrucción del usuario contradice este archivo, señálalo antes de proceder.
