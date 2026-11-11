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

## Pendientes

| Tema                              | Estado                                                                                       |
| --------------------------------- | -------------------------------------------------------------------------------------------- |
| Pago recibido tras expirar        | Se decide en fase 4. Propuesta inicial: reembolso automático, incidente en `audit_logs` y aviso al dueño. |
| Proveedor de pagos                | Se decide en fase 4.                                                                         |

## Consecuencias directas

- Al bloquear agenda (SPEC 8.4), la única forma de resolver citas afectadas en V1 es cancelarlas
  con reembolso, porque no hay reprogramación.
- Todas las citas nacen de la app del cliente, así que el origen de una cita en V1 siempre es
  `CUSTOMER_APP`, y siempre pasan por `PENDING_PAYMENT`.
