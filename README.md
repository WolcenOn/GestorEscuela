# GestorEscuela

Plataforma en desarrollo para organización escolar, ausencias, sustituciones y resiliencia operativa.

## Estado actual

El proyecto ya dispone de:

- solver global de sustituciones con OR-Tools CP-SAT;
- modelo de dominio independiente de FastAPI y SQLAlchemy;
- API FastAPI para centros, planes diarios, resolución, confirmación y reapertura;
- persistencia SQLAlchemy con migraciones Alembic;
- configuración operativa por centro para grupos, franjas, docentes y actividades;
- aislamiento por centro;
- versionado optimista de `DayPlan` y auditoría de resoluciones/transiciones;
- PostgreSQL como base de datos objetivo y pruebas de integración reales en CI;
- identidades persistidas y membresías por centro;
- autorización por membresía cuando se envía `X-Actor-Id`;
- creación de planes únicamente en ruta tenant-scoped.

## Preparar el entorno en Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Levantar PostgreSQL local

Requiere Docker Desktop o un entorno compatible con Docker Compose.

```powershell
docker compose up -d postgres
```

La configuración local por defecto es:

```text
Base de datos: gestor_escuela
Usuario:       gestor
Contraseña:    gestor
Puerto:        5432
```

La aplicación usa por defecto:

```text
postgresql+psycopg://gestor:gestor@localhost:5432/gestor_escuela
```

Se puede sustituir con la variable de entorno `DATABASE_URL`.

## Aplicar migraciones

```powershell
alembic upgrade head
```

## Ejecutar validaciones

```powershell
python -m pytest
ruff check .
mypy src
python simulate.py
```

## Ejecutar la API

```powershell
uvicorn gestor_escuela.api.app:app --reload
```

La documentación OpenAPI queda disponible en `/docs` mientras la API está en ejecución.

## Identidad y membresías

Durante esta fase existe un bootstrap provisional mediante `X-Actor-Role`. Se usa para crear la identidad y membresía administrativa iniciales. Una vez existe un usuario con membresía, las rutas con `school_id` pueden autorizarse con:

```text
X-Actor-Id: <UUID_DEL_USUARIO>
```

La membresía persistida del usuario en ese centro es la fuente de verdad del rol. Enviar además `X-Actor-Role` no permite elevar privilegios cuando existe identidad.

Flujo de bootstrap actual:

1. crear usuario con `POST /users`;
2. asignar o actualizar su membresía con `PUT /schools/{school_id}/memberships`;
3. usar `X-Actor-Id` en las operaciones posteriores del centro.

Los roles actuales son:

- `ADMIN`: configuración, membresías y reapertura;
- `PLANNER`: creación/cálculo/confirmación de planes;
- `VIEWER`: lectura.

La creación de planes está acotada al tenant:

```text
POST /schools/{school_id}/day-plans
```

No existe una ruta global de creación de `DayPlan`.

## Importar configuración de un centro desde JSON

Existe un ejemplo en:

```text
examples/school_configuration.example.json
```

Con la API en ejecución y un centro ya creado:

```powershell
python -m gestor_escuela.import_config `
  --school-id 00000000-0000-0000-0000-000000000001 `
  --file examples/school_configuration.example.json
```

También se puede indicar otra API:

```powershell
python -m gestor_escuela.import_config `
  --school-id 00000000-0000-0000-0000-000000000001 `
  --file .\mi-centro.json `
  --api-url http://127.0.0.1:8000
```

El fichero usa el mismo esquema de validación que `PUT /schools/{school_id}/configuration`.

## Concurrencia

`DayPlan.version` funciona como contador de versión optimista. Las escrituras del ORM se condicionan a la versión conocida de la fila; si otra transacción la modifica antes, la segunda escritura se rechaza como actualización obsoleta. GitHub Actions valida este comportamiento contra PostgreSQL con dos sesiones independientes y también mediante peticiones HTTP concurrentes.

## Estructura principal

```text
src/gestor_escuela/
├── api/
├── domain/
├── persistence/
├── simulation/
├── solver/
└── import_config.py

alembic/
examples/
tests/
docs/adr/
simulate.py
compose.yml
```

## Deuda técnica actual

- `X-Actor-Role` sigue existiendo como mecanismo provisional de bootstrap; no es autenticación real.
- La compatibilidad docente-grupo sigue siendo binaria; faltan requisitos por materia/perfil.
- La equidad usa todavía un contador histórico simple, no ventanas semanal/mensual/trimestral.
- Las explicaciones no enumeran aún el catálogo completo de candidatos descartados.
