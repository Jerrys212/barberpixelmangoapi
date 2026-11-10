# AGENTS.md

API REST con FastAPI + PostgreSQL para un sistema de reservas de una barbería (app móvil de
clientes + panel web del dueño). Autenticación con access token (JWT, corta duración) y refresh
token opaco y rotativo por sesión/dispositivo, guardado hasheado en BD.

Este archivo es la guía para agentes de IA (Claude Code, Codex, Cursor). Léelo completo antes
de escribir código. Las reglas marcadas como **NUNCA** / **SIEMPRE** no son negociables.

## Stack

| Pieza            | Elección                                                  |
| ---------------- | --------------------------------------------------------- |
| Python           | 3.14                                                      |
| Paquetes         | `uv` (nunca `pip` directo)                                |
| Framework        | FastAPI (usa `Annotated[T, Depends(...)]`)                |
| Validación       | Pydantic v2 + `pydantic-settings`                         |
| BD               | PostgreSQL + SQLAlchemy 2.0 **async** + `asyncpg`         |
| Migraciones      | Alembic                                                   |
| JWT              | `PyJWT` (`import jwt`) — **NUNCA** `python-jose`          |
| Hash de password | `pwdlib[argon2]` — **NUNCA** `passlib` ni bcrypt manual   |
| Rate limit (IP)  | `slowapi` (memoria en V1; backend intercambiable a Redis) |
| Tareas periódicas| `APScheduler` en proceso (sin Redis en V1)                |
| HTTP saliente    | `httpx.AsyncClient` (Brevo, proveedor de pagos)           |
| Tests            | `pytest` + `httpx.AsyncClient` + `ASGITransport`, BD real |
| Calidad          | `ruff` (lint + formato), `mypy --strict`                  |

Las dependencias que aún no están instaladas (`slowapi`, `apscheduler`) se agregan con `uv add`
en la fase que las use, no antes.

## Comandos

**SIEMPRE** antepón `uv run` a cualquier comando de Python.

```bash
uv sync                                              # instalar dependencias
uv run fastapi dev src/main.py                       # servidor de desarrollo
uv run pytest -x -q                                  # tests
uv run ruff check --fix . && uv run ruff format .    # lint + formato
uv run mypy src                                      # tipos
uv run alembic revision --autogenerate -m "descripcion"   # nueva migración
uv run alembic upgrade head                          # aplicar migraciones
```

**Definición de terminado:** una tarea NO está terminada hasta que `ruff`, `mypy` y `pytest`
pasan sin errores. No digas "listo" sin haberlos corrido.

### Base de datos local

- PostgreSQL corre en la instancia Docker `dulcecms` (contenedor `strapi-postgres`,
  `localhost:5432`). **No** hay `docker-compose` en este repo.
- Este proyecto usa **su propio usuario** (`barberpixelmango`) y sus propias bases
  (`barberpixelmango` y `barberpixelmango_test`). **NUNCA** uses ni modifiques las bases o
  usuarios de otros proyectos de esa instancia (`strapi`, `portfoliocms`, `dulceatardecer`).
- **NUNCA** ejecutes `REASSIGN OWNED` ni `DROP OWNED` en esa instancia: afectan objetos
  compartidos de otros proyectos.
- **NUNCA** leas ni muestres `.env`; para cambiar una variable edita solo esa línea.

## Estructura (modular por dominio)

```
src/
├── main.py            # crea la app, lifespan, registra routers y exception handlers
├── config.py          # Settings globales (pydantic-settings)
├── database.py        # engine async, sessionmaker, dependencia get_session
├── models.py          # Base declarativa con naming_convention + mixins (timestamps)
├── exceptions.py      # AppError base + handler global
├── scheduler.py       # APScheduler: registro de jobs; arranca en lifespan si SCHEDULER_ENABLED
├── rate_limit.py      # Limiter de slowapi (storage_uri configurable)
├── idempotency/       # tabla y helper para el header Idempotency-Key
├── email/             # EmailSender, ConsoleEmailSender, BrevoEmailSender, EmailSettings
├── auth/
│   ├── router.py      # registro, login, verificación, OTP, refresh, logout, recuperación, sesiones
│   ├── schemas.py     # TokenPair, LoginRequest, RefreshRequest, SessionOut
│   ├── models.py      # RefreshSession, RefreshToken, EmailVerificationCode, PasswordResetCode
│   ├── cli.py         # create-owner, reset-owner-password
│   ├── repository.py  # queries de sesiones y códigos OTP
│   ├── service.py     # login, rotación, revocación, verificación, recuperación
│   ├── security.py    # JWT, hash/verify password, refresh token, HMAC de OTP
│   ├── dependencies.py# CurrentUser, VerifiedCustomer, OwnerUser
│   ├── config.py      # AuthSettings (secretos, expiraciones, límites de OTP)
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
- Todos los routers de dominio se montan bajo **`/api/v1`** en `main.py`
  (`app.include_router(router, prefix="/api/v1")`). Cada router define solo su propio prefijo
  (`/users`, `/services`...). `/health` queda fuera del prefijo.

## Dominio

**Fuente de verdad:** `docs/SPEC.md` (especificación funcional) y `docs/DECISIONS.md`
(decisiones que cierran los puntos abiertos de la spec). Si se contradicen, manda
`DECISIONS.md`. Antes de implementar una funcionalidad, lee la sección correspondiente de la spec.
Si algo no está definido en ninguno de los dos, pregunta; **NUNCA** lo asumas.

### Mapa de módulos

| Módulo         | Responsabilidad                                                                                              | Tablas principales                                            |
| -------------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------- |
| `auth`         | Registro, login, verificación de correo, recuperación, refresh, logout, sesiones por dispositivo y revocación | `refresh_sessions`, `refresh_tokens`, `email_verification_codes`, `password_reset_codes` |
| `users`        | Identidad, roles, perfil del cliente; búsqueda y listado de clientes (admin)                                 | `users`                                                       |
| `business`     | Perfil único del negocio: zona IANA, moneda, buffer, intervalo de slots, retención, ventanas de reserva y cancelación | `business_profile`                                   |
| `catalog`      | Servicios: nombre, descripción, precio (centavos), duración, `image_url` externa, activo/inactivo            | `services`                                                    |
| `schedule`     | Horarios semanales (varios intervalos por día), excepciones, cierres y bloqueos                              | `business_schedules`, `schedule_exceptions`                   |
| `availability` | Cálculo bajo demanda de inicios disponibles. Sin tablas propias: lee `schedule`, `business` y `appointments` | —                                                             |
| `appointments` | Retención temporal, confirmación, cancelación, completar, no-show e historial de estados                     | `appointments`, `appointment_status_history`                  |
| `payments`     | Operaciones de pago, webhooks, conciliación y **reembolsos**                                                 | `payments`, `refunds`, `payment_webhook_events`               |
| `audit`        | Registro de acciones sensibles del dueño                                                                     | `audit_logs`                                                  |

- **No existe un módulo `admin`.** Las operaciones del dueño viven en el router de su módulo
  (p. ej. `POST /services` en `catalog`, `DELETE /sessions/{id}` en `auth`) y se protegen con la
  dependencia de rol `OWNER` (`OwnerUser`).
- `availability` y `appointments` comparten la misma regla de ocupación (cita activa =
  `start_at` hasta `end_at + buffer_snapshot`). Esa regla vive en un solo lugar y ambos la usan.
- `email`, `idempotency`, `scheduler` y `rate_limit` son infraestructura transversal, no
  dominios: no tienen reglas de negocio ni router propio.
- `business_profile` guarda los parámetros editables por el dueño (zona, moneda, intervalo de
  slots, buffer, retención, ventana de cancelación, anticipación mínima y máxima). Sus valores
  iniciales están en `DECISIONS.md`. **NUNCA** los hardcodees en services.

### Invariantes críticas

- **SIEMPRE** guarda en cada cita un snapshot del servicio al reservar: nombre, precio, moneda,
  duración y buffer. **NUNCA** recalcules una cita existente a partir de `services` o
  `business_profile`; la FK al servicio es solo para navegación.
- **SIEMPRE** guarda instantes como `TIMESTAMPTZ` (`DateTime(timezone=True)`) en UTC, y convierte
  horarios locales con la zona IANA del negocio (`zoneinfo.ZoneInfo(business.timezone)`).
  **NUNCA** uses offsets fijos (`UTC-6`, `timedelta(hours=-6)`) ni la hora local del servidor.
  Los horarios semanales y excepciones son hora local de pared (`time`/`date`) que se resuelven a
  instantes al calcular.
- **SIEMPRE** toma el precio y la moneda del servicio guardado en backend. **NUNCA** aceptes un
  precio, importe o duración enviado por el cliente.
- **SIEMPRE** maneja importes como enteros en centavos (`amount_cents: int`, `BigInteger`) junto
  a una columna `currency` (`CHAR(3)`, `MXN` en V1). **NUNCA** uses `float` para dinero.
- **SIEMPRE** mantén el estado de la cita separado del estado del pago y del reembolso (columnas y
  enums distintos). Una cita `CANCELLED`, `EXPIRED` o `COMPLETED` **NUNCA** vuelve a `CONFIRMED`
  por un webhook tardío.
- **SIEMPRE** procesa los webhooks de forma idempotente: verifica la firma antes de nada, guarda el
  id del evento en `payment_webhook_events` con restricción `UNIQUE`, y comprueba el estado actual
  de la cita y del pago antes de cambiarlo. Un evento repetido **NUNCA** duplica pagos, citas ni
  reembolsos.
- **SIEMPRE** valida en backend la ventana de cancelación del cliente: 24 h exactas antes del
  instante de inicio (`start_at - now >= cancellation_window`), no "el día anterior". La ventana se
  lee de `business_profile`. Ocultar el botón en la app no cuenta como validación.
- **SIEMPRE** crea una cita revalidando horario, excepciones y solapamientos dentro de la misma
  transacción, con lock del calendario y una restricción de exclusión en BD contra solapamientos
  de citas activas. **NUNCA** confíes en la disponibilidad que vio el cliente.
- **SIEMPRE**, dentro de esa misma transacción y **antes** de insertar, pasa a `EXPIRED` (con su
  entrada en el historial de estados) las retenciones `PENDING_PAYMENT` con `expires_at <= now`
  que choquen con el rango solicitado. La restricción de exclusión las sigue viendo activas
  mientras estén en `PENDING_PAYMENT`, así que la tarea programada **NUNCA** es la responsable de
  liberar horarios: es solo limpieza.
- **SIEMPRE** valida la anticipación mínima y el horizonte máximo de `business_profile` en el
  backend, al consultar disponibilidad y al crear la cita.
- **SIEMPRE** exige el header `Idempotency-Key` al crear una reserva y al crear un pago. Cancelar
  es idempotente por estado: cancelar algo ya `CANCELLED` devuelve el mismo resultado, sin crear un
  segundo reembolso.
- **SIEMPRE** que un `CUSTOMER` sin correo verificado intente reservar o pagar, responde 403 con
  el código de dominio `EMAIL_NOT_VERIFIED`.
- **SIEMPRE** que se revoque una sesión, se cancele una cita, se cambie un horario, se cree un
  bloqueo o se inicie un reembolso desde el panel, registra la acción en `audit`.

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

Referencia funcional: `docs/SPEC.md` sección 6.

### Roles

- Dos roles: `OWNER` y `CUSTOMER` (enum en `users.role`).
- El registro público **SIEMPRE** crea `CUSTOMER`. El rol **NUNCA** se acepta en un payload.
- La cuenta `OWNER` se crea y se recupera **solo** con comandos de consola, **NUNCA** por la API
  (`DECISIONS.md`):
  - `uv run python -m src.auth.cli create-owner`: crea el único `OWNER` (falla si ya existe uno).
  - `uv run python -m src.auth.cli reset-owner-password`: fija una contraseña nueva al `OWNER` y
    revoca todas sus sesiones.
  - Los comandos piden la contraseña de forma interactiva (`getpass`), **NUNCA** como argumento.
- El registro exige nombre, correo, contraseña y **teléfono** (obligatorio).
- Un usuario sin correo verificado **puede** iniciar sesión, pero no reservar ni pagar: 403 con
  código `EMAIL_NOT_VERIFIED`.
- Dependencias en `auth/dependencies.py`:
  - `CurrentUser`: usuario autenticado con sesión vigente.
  - `VerifiedCustomer`: `CUSTOMER` con correo verificado (si no, 403 `EMAIL_NOT_VERIFIED`).
  - `OwnerUser`: rol `OWNER`; responde 403 a cualquier otro rol.
- La autorización por rol **y por propiedad del recurso** se valida en backend. Un cliente
  **NUNCA** puede leer ni modificar citas, pagos o sesiones de otro cliente.

### Access token

- JWT firmado (HS256 con `AUTH_SECRET_KEY` de ≥32 bytes, o RS256 si hay varios servicios).
- Vida corta: **15 minutos** (`ACCESS_TOKEN_EXPIRE_MINUTES`).
- Claims: `sub` (user id), `sid` (id de la sesión), `role`, `exp`, `iat`, `jti`, `type="access"`.
- Al decodificar: **SIEMPRE** pasa `algorithms=[...]` explícito, valida `exp` y verifica
  `type == "access"`. Un refresh token **NUNCA** debe funcionar como access token.
- `get_current_user` comprueba que la sesión `sid` siga vigente (no revocada ni expirada). Revocar
  una sesión invalida de inmediato sus access tokens, no solo su renovación.
- Se envía en `Authorization: Bearer <token>`.

### Sesiones y refresh token

- `refresh_sessions`: una fila por sesión/dispositivo; es la "familia" de tokens.
  Columnas: `id, user_id, device_name, platform (ANDROID | IOS | WEB | OTHER), user_agent,
  ip_address, created_at, last_used_at, expires_at, revoked_at, revoked_reason`. La plataforma y
  el nombre del dispositivo los reporta el cliente en el login.
- `refresh_tokens`: historial de tokens de cada sesión.
  Columnas: `id, session_id, token_hash (unique), created_at, rotated_at, replaced_by_id`.
  Solo un token por sesión tiene `rotated_at IS NULL` (el vigente).
- El refresh token es **opaco**, no JWT: `secrets.token_urlsafe(64)`. En BD se guarda **solo el
  hash** (SHA-256), **NUNCA** el valor en claro.
- Vida: **7 días** (`REFRESH_TOKEN_EXPIRE_DAYS`); cada refresh mueve `expires_at` de la sesión.
- **Rotación obligatoria:** cada `POST /auth/refresh`, con lock de la fila de la sesión
  (`SELECT ... FOR UPDATE`), marca el token usado con `rotated_at=now` y `replaced_by_id`, inserta
  el nuevo, actualiza `last_used_at` y emite un par nuevo para la misma sesión.
- **Detección de reuso:** si llega un token ya rotado, se revoca la sesión
  (`revoked_reason="reuse_detected"`) y se responde 401. Es señal de robo.
- **Gracia de 30 s** (`REFRESH_REUSE_GRACE_SECONDS`): si el token rotado es el **inmediatamente
  anterior** (su `replaced_by_id` apunta al token vigente) y `now - rotated_at <= 30 s`, no se
  revoca nada: se trata como un refresh concurrente de la app y se rota de nuevo para la misma
  sesión. Fuera de ese caso, cualquier token viejo revoca la sesión.
- `last_used_at` se actualiza en cada refresh. Es "última actividad", **NUNCA** se presenta como
  presencia en tiempo real (SPEC 6.3).
- `POST /auth/logout` revoca la sesión actual. El dueño puede revocar una sesión concreta (las
  demás del usuario siguen vigentes) o todas las de un usuario. Cambiar o recuperar la contraseña
  revoca todas las sesiones del usuario.

### Códigos OTP (verificación de correo y recuperación de contraseña)

- Códigos de **6 dígitos** generados con `secrets.randbelow(10**6)` y rellenados con ceros.
- **NUNCA** se guardan en claro: se guarda `HMAC-SHA256(OTP_HMAC_SECRET, f"{purpose}:{user_id}:{code}")`.
  `OTP_HMAC_SECRET` es un secreto distinto de `AUTH_SECRET_KEY`. Compara con
  `hmac.compare_digest`.
- Tablas separadas `email_verification_codes` y `password_reset_codes`, con `user_id, code_hmac,
  expires_at, attempts, consumed_at, created_at`.
- Límites (en `AuthSettings`):

  | Regla                       | Valor  | Variable                  |
  | --------------------------- | ------ | ------------------------- |
  | Vigencia del código         | 10 min | `OTP_EXPIRE_MINUTES`      |
  | Intentos por código         | 5      | `OTP_MAX_ATTEMPTS`        |
  | Espera entre reenvíos       | 60 s   | `OTP_RESEND_COOLDOWN_SECONDS` |
  | Reenvíos por hora por cuenta| 5      | `OTP_MAX_RESENDS_PER_HOUR` |

- Cada código es de uso único. Al emitir uno nuevo se invalidan los anteriores del mismo propósito.
  Agotar los intentos invalida el código.
- Respuestas genéricas: solicitar verificación o recuperación responde igual exista o no el correo.
- Confirmar la recuperación cambia la contraseña y revoca las sesiones, pero **NUNCA** inicia sesión
  automáticamente: el usuario debe hacer login.

### Rate limiting

- **Por IP:** `slowapi` en `src/rate_limit.py`, aplicado a login, registro, OTP, recuperación,
  creación de reservas y pagos. Almacenamiento en memoria en V1 vía `RATE_LIMIT_STORAGE_URI`
  (`memory://`); pasar a Redis es cambiar esa variable, sin tocar código. En memoria el límite es
  por proceso: se acepta en V1.
- **Por cuenta y por OTP:** en PostgreSQL, porque son los críticos y deben sobrevivir reinicios:
  intentos fallidos de login por cuenta (`users.failed_login_attempts`, `users.locked_until`),
  intentos por código (`attempts`) y reenvíos (contando códigos emitidos en la última hora).
- Una cuenta bloqueada responde igual que credenciales inválidas (401 genérico), para no revelar
  que existe.

### Passwords y respuestas

- Hash con `pwdlib` (argon2). **NUNCA** guardes ni compares passwords en claro.
- Login fallido: mismo mensaje y mismo status (401 "Credenciales inválidas") exista o no el
  usuario. Incluye header `WWW-Authenticate: Bearer`.
- **NUNCA** loguees passwords, tokens, hashes ni el header `Authorization`.
- `CurrentUser = Annotated[User, Depends(get_current_user)]` (y sus variantes `VerifiedCustomer`
  y `OwnerUser`) en `auth/dependencies.py` es la única forma de obtener el usuario autenticado.
  Un endpoint sin ninguna de estas dependencias es público: hazlo solo si es intencional (p. ej.
  catálogo, perfil público del negocio, disponibilidad, webhooks).

## Errores

- Errores de negocio heredan de `AppError(message, status_code)` en `src/exceptions.py`; un
  handler global los convierte en JSON. Usa 404, 409, 403, 401 según corresponda.
- Cada error de dominio lleva un **código estable** en mayúsculas que la app puede interpretar
  (`{"code": "SLOT_UNAVAILABLE", "detail": "..."}`): `SLOT_UNAVAILABLE`, `HOLD_EXPIRED`,
  `CANCELLATION_WINDOW_CLOSED`, `SESSION_REVOKED`, `EMAIL_NOT_VERIFIED`, etc. El mensaje puede
  cambiar; el código **NUNCA**.
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
- Las variables documentadas viven en `.env.example`, con valores de ejemplo. Toda variable nueva
  se agrega ahí en el mismo cambio.

## Correo

- `src/email/` define un `Protocol` `EmailSender` con `async def send(message: EmailMessage) -> None`.
- Dos implementaciones:
  - `ConsoleEmailSender`: no sale a la red; para tests y desarrollo sin red.
  - `BrevoEmailSender`: API transaccional de Brevo (`POST https://api.brevo.com/v3/smtp/email`,
    header `api-key`) con `httpx.AsyncClient` y timeout explícito. **NUNCA** SMTP ni el SDK de
    Brevo.
- Se elige con `EMAIL_BACKEND=console|brevo` (`EmailSettings` en `src/email/config.py`, con
  `BREVO_API_KEY`, `EMAIL_SENDER_ADDRESS`, `EMAIL_SENDER_NAME`). Los services reciben el sender por
  inyección de dependencias, nunca lo instancian.
- **NUNCA** loguees la API key, el cuerpo del correo ni los códigos OTP. Un fallo de envío se
  registra sin datos sensibles y **no** cambia la respuesta genérica al cliente.
- Los tests **SIEMPRE** usan `ConsoleEmailSender` o un fake vía `app.dependency_overrides`;
  **NUNCA** mandan correos reales.
- Fase 1 solo envía verificación y recuperación. Confirmación, cancelación y reembolso se agregan
  en sus fases.

## Tareas programadas

- `APScheduler` (`AsyncIOScheduler`) en `src/scheduler.py`, arrancado y detenido en el `lifespan`
  **solo** si `SCHEDULER_ENABLED=true`. Con varios workers de uvicorn, exactamente un proceso lo
  habilita.
- Todos los jobs son idempotentes por sí mismos (p. ej. `UPDATE ... WHERE status =
  'PENDING_PAYMENT' AND expires_at <= now()`), así que correrlos dos veces no causa daño.
- Jobs de V1: limpiar retenciones vencidas (solo limpieza, ver invariantes), limpiar códigos OTP
  vencidos, y desde la fase 4, conciliar reembolsos y pagos tardíos.
- Cada job abre su propia sesión con `session_factory` y hace su propio commit; **NUNCA** usa
  `get_session`.

## Idempotencia

- `Idempotency-Key` (header) es **obligatorio** en `POST` de crear reserva y crear pago.
- `src/idempotency/` guarda `(user_id, endpoint, key)` como `UNIQUE`, junto con el hash del body y
  la respuesta (status y cuerpo).
- Misma clave y mismo body: devuelve la respuesta guardada sin repetir la operación. Misma clave
  con otro body: 409 `IDEMPOTENCY_KEY_REUSED`.
- Cancelar **no** usa clave: es idempotente por estado.

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
  refresh usado como access (401), rotación de refresh, reuso de refresh rotado (revoca la sesión),
  refresh concurrente dentro de los 30 s de gracia (no revoca), reuso fuera de la gracia (revoca),
  logout, endpoint protegido sin token (401), access token de una sesión revocada (401), revocar
  una sesión no afecta las demás del usuario, endpoint de `OWNER` con un `CUSTOMER` (403), OTP
  incorrecto / expirado / ya usado / intentos agotados, reenvío antes de 60 s y sexto reenvío en
  una hora (rechazados), usuario sin verificar intentando reservar (403 `EMAIL_NOT_VERIFIED`),
  registro como `OWNER` imposible por la API.
- Tests de dominio obligatorios: los criterios de aceptación de `docs/SPEC.md` sección 11
  (doble reserva concurrente, buffer, snapshot, expiración a los 10 min, webhook repetido y
  tardío, ventana de 24 h, bloqueo con citas afectadas, zona horaria).

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
