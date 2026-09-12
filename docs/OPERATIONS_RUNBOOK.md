# Runbook operativo · GestorEscuela

Este documento describe el gate operativo de Fase 0 para PostgreSQL + Railway. Los secretos se configuran directamente en Railway o en el gestor de secretos correspondiente; **no se copian en tickets, logs ni documentación**.

## 1. Variables mínimas de producción

Comprobar antes de cada despliegue:

```text
DATABASE_URL=<gestionada por Railway/PostgreSQL>
CORS_ORIGINS=https://wolcenon.github.io
ALLOW_LEGACY_ROLE_BOOTSTRAP=false
AUTH_SESSION_TTL_HOURS=12
AUTH_SESSION_IDLE_MINUTES=120
AUTH_SESSION_TOUCH_INTERVAL_MINUTES=5
AUTH_LOGIN_MAX_FAILURES=5
AUTH_LOGIN_WINDOW_MINUTES=15
AUTH_LOGIN_BLOCK_MINUTES=15
PASSWORD_RESET_TTL_MINUTES=30
PASSWORD_RESET_FRONTEND_URL=https://wolcenon.github.io/Horario-PT-AL/
MAX_REQUEST_BODY_BYTES=4194304
ENABLE_HSTS=true
```

Para recuperación de contraseña se necesitan además `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` y `SMTP_STARTTLS`. `SMTP_PASSWORD` debe introducirse únicamente como secreto en Railway.

## 2. Despliegue

`railway.json` ejecuta antes del arranque:

```text
PYTHONPATH=src python -m gestor_escuela.deploy
```

Ese paso aplica `alembic upgrade head`. La aplicación solo arranca después con Uvicorn y Railway comprueba `/health`.

Antes de promover una revisión:

1. confirmar que `Backend integration CI` está verde en el SHA exacto;
2. comprobar que no hay migraciones Alembic con más de una cabeza;
3. crear un backup de PostgreSQL antes de una migración destructiva o de alto riesgo;
4. verificar las variables anteriores, especialmente `ALLOW_LEGACY_ROLE_BOOTSTRAP=false`;
5. desplegar backend antes que frontend cuando haya cambios de contrato coordinados;
6. ejecutar smoke test de `/health`, login Bearer y una lectura tenant-scoped después del despliegue.

## 3. Crear backup PostgreSQL

El script usa `DATABASE_URL` y produce un dump custom de PostgreSQL sin propietarios ni privilegios del origen:

```bash
DATABASE_URL='postgresql+psycopg://...' \
  bash scripts/backup_postgres.sh /ruta/segura/gestor-escuela.dump
```

El fichero se crea con `umask 077`. Al terminar se valida con `pg_restore --list`.

El dump contiene datos personales del centro. Debe guardarse cifrado, con acceso restringido y fuera del repositorio. Nunca debe subirse a GitHub ni adjuntarse a una incidencia.

## 4. Restaurar

La restauración sustituye el contenido del destino indicado por `DATABASE_URL`. **No ejecutar contra producción sin una decisión explícita y una copia adicional del estado actual.**

```bash
DATABASE_URL='postgresql+psycopg://.../base_destino' \
  bash scripts/restore_postgres.sh /ruta/segura/gestor-escuela.dump
```

Después comprobar:

```sql
SELECT version_num FROM alembic_version;
```

y ejecutar `alembic upgrade head` si el backup procede de una versión anterior de la aplicación.

## 5. Ensayo de restauración

CI realiza en cada cambio del backend:

1. migración de una base limpia hasta la revisión `0015`;
2. actualización desde `0015` hasta `head`;
3. `pg_dump` de la base migrada;
4. creación de una segunda base PostgreSQL vacía;
5. restauración del dump;
6. comparación de la revisión Alembic y del número de tablas públicas entre origen y restauración.

Este ensayo demuestra que el mecanismo básico de backup/restauración funciona, pero no sustituye un ejercicio periódico sobre una copia de producción con datos anonimizados o bajo el procedimiento de seguridad del responsable del centro.

## 6. Incidente de despliegue

Si el backend nuevo falla tras migrar:

1. no modificar manualmente tablas para “arreglar” el despliegue;
2. conservar logs y `X-Request-Id` relevantes sin copiar cuerpos con datos personales;
3. determinar si el fallo es de aplicación o esquema;
4. si la revisión anterior es compatible con el esquema nuevo, revertir únicamente la aplicación;
5. si es imprescindible restaurar datos, crear primero un backup del estado fallido y restaurar en una base de verificación antes de sustituir producción;
6. documentar el incidente y añadir una regresión a CI.

Las migraciones Alembic con pérdida de datos requieren un plan de reversión específico antes de desplegarse.

## 7. Gate de GitHub antes de fusionar a `main`

Configurar en ambos repositorios una regla/ruleset para `main` que, como mínimo:

- requiera pull request;
- bloquee push directo a `main`;
- requiera que la rama esté actualizada antes de fusionar cuando sea viable;
- exija los checks de CI correspondientes;
- impida fusionar mientras los checks estén pendientes o rojos.

Para GestorEscuela el check obligatorio debe incluir `Backend integration CI / quality`. Para Horario-PT-AL deben ser obligatorios los jobs de validación y E2E del workflow de integración.

Esta conexión de GitHub no tiene permisos administrativos para aplicar protección de ramas; la regla debe configurarse desde GitHub por un administrador del repositorio y comprobarse antes de la fusión final.

## 8. Gate de Fase 0

No considerar Fase 0 lista para fusión final hasta confirmar conjuntamente:

- CI backend verde incluyendo migración, backup y restore;
- CI frontend verde y Pages desplegado;
- `ALLOW_LEGACY_ROLE_BOOTSTRAP=false` en Railway;
- SMTP configurado y recuperación de contraseña probada en producción o staging;
- rulesets/required checks de `main` activos en ambos repositorios;
- backup real creado y restauración ensayada al menos en un entorno no productivo;
- documentación y checklist revisados;
- ninguna rama temporal accidental se fusiona en `main`.
