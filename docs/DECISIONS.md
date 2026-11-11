# Decisiones de V1

Cierra los puntos abiertos de `docs/SPEC.md` (sección 10). Si este archivo y la spec se
contradicen, manda este archivo. Toda decisión nueva se agrega aquí con su fecha.

## Producto (10 de noviembre de 2026)

| Tema                       | Decisión para V1                                                                       |
| -------------------------- | -------------------------------------------------------------------------------------- |
| Stack                      | Python 3.14 + FastAPI + PostgreSQL + SQLAlchemy async + Alembic (ver `AGENTS.md`).     |
| Cuenta OWNER               | Se crea con un comando de consola, nunca por la API. Si pierde acceso, se recupera con otro comando de consola. |
| Intervalo de slots         | Guardado en `business_profile` (editable después).                                    |
| Anticipación de reservas   | Mínimo 1 h antes del inicio; máximo 30 días hacia adelante. Guardado en `business_profile`. |
| Cancelación del cliente    | Hasta 24 horas exactas antes del instante de inicio. Guardado en `business_profile`.   |
| Reprogramar                | No en V1.                                                                              |
| Citas creadas por el dueño | No en V1.                                                                              |
| Notificaciones             | Solo correo. Fase 1: verificación y recuperación. Confirmación, cancelación y reembolso en sus fases. |
| Proveedor de correo        | Brevo, por SMTP (relay de Brevo) con STARTTLS en el puerto 587.                        |
| Proveedor de pagos         | Stripe o Mercado Pago. Se puede decidir hasta la fase 4; antes no hace falta.          |
| Moneda e importes          | Solo MXN en V1, pero se guarda la columna de moneda. Importes en centavos como entero. |
| Imagen del servicio        | URL externa. Sin subida de archivos.                                                   |
| Correo no verificado       | Puede iniciar sesión, pero no reservar ni pagar (403 con error de dominio identificable). |
| Teléfono                   | Obligatorio al registrarse: exactamente 10 dígitos de México, solo números (`5512345678`). Sin `+52`, espacios ni guiones. Reemplaza a E.164 (10 de noviembre de 2026): en México el formato habitual es de 10 dígitos. |

### Configuración del negocio

`business_profile` guarda, editables por el dueño: zona IANA, moneda, intervalo de slots, buffer,
duración de la retención, ventana de cancelación y anticipación mínima/máxima.

| Campo                         | Valor inicial         |
| ----------------------------- | --------------------- |
| Zona horaria                  | `America/Mexico_City` |
| Moneda                        | `MXN`                 |
| Intervalo de slots            | 10 min                |
| Buffer de preparación         | 10 min                |
| Retención `PENDING_PAYMENT`   | 10 min                |
| Ventana de cancelación        | 24 h                  |
| Anticipación mínima           | 1 h                   |
| Horizonte máximo              | 30 días               |

Qué se congela en la cita y qué se lee del perfil vigente:

| Parámetro                         | Dónde se lee                  | Por qué                                                              |
| --------------------------------- | ----------------------------- | -------------------------------------------------------------------- |
| Nombre, precio y moneda del servicio | Snapshot de la cita        | Es lo que el cliente compró.                                         |
| Duración y buffer                 | Snapshot de la cita           | Definen cuánto ocupa la cita en la agenda.                           |
| Ventana de cancelación            | Snapshot de la cita           | El cliente pagó bajo la política vigente al reservar; si el dueño la cambia (p. ej. de 24 h a 48 h), no afecta citas ya creadas. |
| Anticipación mínima y máxima      | Perfil vigente                | Solo aplica en el momento de reservar.                               |
| Intervalo de slots y retención    | Perfil vigente                | Solo aplican al calcular disponibilidad y al crear la retención.     |

## Técnicas (10 de noviembre de 2026)

| Tema                   | Decisión                                                                                                   |
| ---------------------- | ---------------------------------------------------------------------------------------------------------- |
| Tareas programadas     | APScheduler dentro del proceso, sin Redis. Un solo proceso ejecuta el scheduler (`SCHEDULER_ENABLED`) y todos los jobs son idempotentes. |
| Retenciones vencidas   | La transacción de reserva pasa a `EXPIRED` las retenciones vencidas que choquen con el rango antes de insertar. El job programado es solo limpieza. |
| Rate limiting por IP   | `slowapi` en memoria, con el backend de almacenamiento configurable para pasar a Redis después. 10 solicitudes por minuto por IP en login, OTP y recuperación. |
| Bloqueo de cuenta      | 5 intentos fallidos de login → bloqueo de 15 min. La respuesta es genérica: no revela si el correo existe ni si la cuenta está bloqueada. |
| Límites por cuenta/OTP | En PostgreSQL (intentos fallidos de login, intentos por código, reenvíos), para que sobrevivan reinicios.  |
| Refresh tokens         | Tabla de historial por sesión. Cualquier reuso de un token viejo revoca la sesión, con 30 s de gracia para el token inmediatamente anterior (refresh concurrentes). |
| OTP                    | 10 min de vigencia, 5 intentos por código, 60 s entre reenvíos y máximo 5 reenvíos por hora por cuenta.   |
| Correo                 | Interfaz `EmailSender` con `ConsoleEmailSender` y `SmtpEmailSender` (`aiosmtplib`, STARTTLS, puerto 587). Se elige con `EMAIL_BACKEND=console\|smtp`. Credenciales en `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` y `SMTP_FROM`. Los tests nunca mandan correos reales. |
| Versionado de API      | Prefijo `/api/v1`.                                                                                         |
| Idempotencia           | Header `Idempotency-Key` obligatorio al crear reserva y al crear el pago. Cancelar es idempotente por estado, sin clave. |
| Base de datos local    | Base y usuario propios (`barberpixelmango`) dentro de la instancia `dulcecms`. Nunca se comparte la BD de otro proyecto. |

## Catálogo, agenda y disponibilidad (10 de noviembre de 2026)

| Tema                          | Decisión                                                                                       |
| ----------------------------- | ---------------------------------------------------------------------------------------------- |
| Perfil público del negocio    | `GET /business` es público: nombre, teléfono y dirección (opcionales), zona horaria y la configuración que usa la app. |
| Cambios al perfil             | Solo el dueño. Se auditan (`BUSINESS_UPDATED`) con valor anterior y nuevo de cada campo cambiado. La moneda no se edita por la API en V1. |
| Servicios inactivos           | `GET /services` lista solo activos. `?include_inactive=true` es solo para `OWNER`; cualquier otro (cliente o anónimo) recibe 403. Los servicios no se borran, se desactivan. |
| Horario semanal               | Varios intervalos por día, sin encimarse. `PUT /schedule/weekly` reemplaza la semana completa y se audita. |
| Tipos de excepción            | `CLOSED` (día completo), `SPECIAL_HOURS` (reemplaza el horario semanal de esa fecha) y `BLOCK` (resta un rango; el dueño no está). Todas en hora local de pared. |
| Reglas de excepciones         | No se permiten fechas pasadas (según la fecha local del negocio; hoy sí). Una fecha no puede tener `CLOSED` y `SPECIAL_HOURS` a la vez, ni dos `SPECIAL_HOURS` encimados. |
| Cierre de varios días         | Se guarda una fila `CLOSED` por día, pero el endpoint acepta `date_from`/`date_to` y crea todas en una sola transacción (todo o nada), auditado como una sola acción. Máximo 366 días. |
| Rejilla de inicios            | Cada `slot_interval_minutes`, contando desde el inicio de cada intervalo abierto. Intervalos contiguos se tratan como uno. |
| Servicio y buffer             | El servicio debe caber completo dentro del horario abierto. El buffer puede pasarse de la hora de cierre, pero **no** puede pisar un bloqueo ni otra cita. |
| Horizonte                     | Se mide por instante: `inicio ≤ ahora + booking_horizon_days`. La anticipación mínima igual: `inicio ≥ ahora + min_notice_minutes`. |
| Cambio de horario (DST)       | Una hora local que no existe se descarta. La conversión siempre usa `zoneinfo` con la zona del perfil (paquete `tzdata`, necesario en Windows). |

## Pendientes

| Tema                              | Estado                                                                                       |
| --------------------------------- | -------------------------------------------------------------------------------------------- |
| Cambios de agenda con citas afectadas | Fase 3. Responder 409 con la lista de citas afectadas en lugar de guardar cuando un bloqueo, un cierre, un horario especial o un cambio del horario semanal deje citas activas fuera del horario. En fase 2 se guardan sin esa revisión porque aún no existen citas. |
| Pago recibido tras expirar        | Se decide en fase 4. Propuesta inicial: reembolso automático, incidente en `audit_logs` y aviso al dueño. |
| Proveedor de pagos                | Se decide en fase 4.                                                                         |

## Consecuencias directas

- Al bloquear agenda (SPEC 8.4), la única forma de resolver citas afectadas en V1 es cancelarlas
  con reembolso, porque no hay reprogramación.
- Todas las citas nacen de la app del cliente, así que el origen de una cita en V1 siempre es
  `CUSTOMER_APP`, y siempre pasan por `PENDING_PAYMENT`.
