# GestorEscuela

Backend multiusuario para planificación académica, operativa diaria, ausencias, sustituciones y escenarios compartidos del Planificador del centro.

## Estado actual

La rama de integración incluye:

- FastAPI + PostgreSQL + SQLAlchemy + Alembic;
- autenticación por correo/contraseña con sesiones Bearer opacas;
- roles `ADMIN`, `PLANNER` y `VIEWER` obtenidos de la membresía persistida del centro;
- aislamiento multi-tenant por `school_id` con regresiones entre centros;
- throttling de login, expiración absoluta y por inactividad, listado/revocación de sesiones;
- cambio y recuperación de contraseña mediante token temporal de un solo uso;
- invitaciones y membresías por centro;
- cursos académicos, escenarios y snapshots compartidos;
- configuración académica y operativa por centro;
- planificación diaria y solver de sustituciones con OR-Tools CP-SAT;
- auditoría semántica sin almacenar cuerpos de peticiones;
- CI con Ruff, Mypy, PostgreSQL/Alembic, tests, solver y Playwright;
- verificación automática de actualización de esquema, backup y restauración PostgreSQL.

El mecanismo antiguo `X-Actor-Id` / `X-Actor-Role` existe únicamente para migraciones de instalaciones previas. `ALLOW_LEGACY_ROLE_BOOTSTRAP` es `false` por defecto y debe permanecer `false` en producción.

## Preparar el entorno

En PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
docker compose up -d postgres
alembic upgrade head
```

La configuración PostgreSQL local por defecto es:

```text
Base de datos: gestor_escuela
Usuario:       gestor
Contraseña:    gestor
Puerto:        5432
URL:           postgresql+psycopg://gestor:gestor@localhost:5432/gestor_escuela
```

Se puede sustituir con `DATABASE_URL`.

## Ejecutar validaciones

```powershell
ruff check .
mypy src
python -m pytest
python simulate.py
```

El workflow de integración añade PostgreSQL real, migración desde una revisión anterior y un ensayo de `pg_dump` + restauración.

## Ejecutar la aplicación

La aplicación completa, incluida la UI operativa embebida, se inicia con:

```powershell
$env:PYTHONPATH="src"
python -m uvicorn gestor_escuela.web:app --reload
```

La documentación OpenAPI queda en `/docs` y el healthcheck en `/health`.

## Autenticación y cuentas

La vía normal de alta es:

```text
POST /auth/register-school
```

Crea en una sola operación la primera cuenta, sus credenciales, el centro, la membresía `ADMIN` y una sesión Bearer.

El acceso posterior utiliza:

```text
POST /auth/login
Authorization: Bearer <token>
```

El token bruto no se persiste en PostgreSQL: se almacena su digest. Las rutas tenant-scoped validan que el usuario autenticado tenga membresía en el `school_id` solicitado; enviar cabeceras de rol no permite elevar privilegios.

Rutas principales de cuenta:

```text
GET    /auth/me
GET    /auth/sessions
DELETE /auth/sessions/{session_id}
POST   /auth/logout
POST   /auth/logout-all
POST   /auth/password/change
POST   /auth/password/reset-request
POST   /auth/password/reset-confirm
GET    /auth/audit-log
```

La recuperación de contraseña devuelve siempre la misma respuesta para correos existentes o inexistentes. Los tokens son aleatorios, se guardan únicamente hasheados, caducan y solo pueden usarse una vez. El envío requiere SMTP configurado en producción.

## Roles y aislamiento

Los roles son:

- `ADMIN`: configuración, membresías, invitaciones y operaciones administrativas;
- `PLANNER`: planificación, cálculo y gestión operativa;
- `VIEWER`: lectura.

El rol efectivo procede siempre de la membresía persistida para ese centro. La matriz de regresión intenta leer y modificar recursos de un segundo centro con un Bearer válido del primero y exige `403`.

## Auditoría

Las mutaciones registran metadatos mínimos: `request_id`, centro cuando aplica, actor, rol, `event_type`, método, ruta, resultado y fecha. No se guardan cuerpos de peticiones ni respuestas.

Ejemplos de eventos semánticos:

```text
auth.password.change
auth.session.revoke
membership.update
membership.invitation.create
academic.configuration.replace
planning.scenario.snapshot.save
operations.day_plan.solve
```

Los administradores consultan la auditoría del centro en `/schools/{school_id}/audit-log`; cada usuario autenticado puede consultar los eventos atribuibles a su propia cuenta en `/auth/audit-log`.

## Backup y restauración

Crear un backup custom de PostgreSQL:

```bash
DATABASE_URL='postgresql+psycopg://...' \
  bash scripts/backup_postgres.sh /ruta/segura/gestor-escuela.dump
```

Restaurarlo en una base de destino:

```bash
DATABASE_URL='postgresql+psycopg://.../destino' \
  bash scripts/restore_postgres.sh /ruta/segura/gestor-escuela.dump
```

Los dumps pueden contener datos personales y nunca deben almacenarse en GitHub. El procedimiento completo y el gate de despliegue están en `docs/OPERATIONS_RUNBOOK.md`.

## Importación de configuración

Existe un ejemplo en `examples/school_configuration.example.json`. La importación legacy se conserva únicamente para migraciones y requiere autorización válida según el estado de la instalación; no es el flujo recomendado para altas nuevas.

## Concurrencia

`DayPlan.version` usa versionado optimista. Si otra transacción modifica el plan antes de una escritura, la actualización obsoleta se rechaza. CI verifica este comportamiento contra PostgreSQL con sesiones independientes y peticiones concurrentes.

## Documentación operativa

- `docs/OPERATIONS_RUNBOOK.md`: despliegue, backup, restore y gate de Fase 0.
- `docs/DATA_RETENTION_AND_DELETION.md`: política técnica propuesta de retención, eliminación y anonimización.
- `docs/adr/`: decisiones arquitectónicas.

## Estructura principal

```text
src/gestor_escuela/
├── api/
├── domain/
├── persistence/
├── simulation/
└── solver/

alembic/
scripts/
examples/
tests/
docs/
simulate.py
compose.yml
railway.json
```

## Despliegue Railway

`railway.json` ejecuta `python -m gestor_escuela.deploy` antes del arranque para aplicar migraciones y después inicia Uvicorn. En producción se debe verificar expresamente `ALLOW_LEGACY_ROLE_BOOTSTRAP=false`, HSTS activo y los orígenes CORS esperados. Las credenciales SMTP y de base de datos se configuran únicamente como secretos del entorno.