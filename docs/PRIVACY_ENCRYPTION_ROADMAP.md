# Privacidad y cifrado del Planificador del centro

Estado: hoja de ruta técnica, **no equivale a cifrado ya implementado**.
Rama: `integracion-horario-pt-al`. No modificar `main` sin revisión explícita.

## Objetivo y límites

Minimizar los datos identificativos necesarios para planificar horarios académicos,
apoyos PT/AL y operativa diaria. Permitir acceso desde distintos dispositivos
autorizados, conservando aislamiento por centro y funcionamiento offline controlado.

La información PT/AL, las notas de texto libre y los metadatos asociados a alumnos
pueden ser datos personales, incluso cuando se sustituyen nombres por UUID.
**Seudonimizar no es anonimizar**. Cifrar PostgreSQL no evita filtraciones por un
backend comprometido o por una sesión con permisos excesivos. Se exige defensa en
profundidad y evaluación organizativa/jurídica antes de utilizar datos reales.

## Fase 0. Contención y mapa de exposición (en curso)

- [x] Lectura del snapshot JSON completo: solo ADMIN/PLANNER. VIEWER obtiene 403.
- [x] Lectura de matrícula identificada, incluyendo observaciones PT/AL: solo ADMIN/PLANNER.
- [x] Regresión de roles con tokens Bearer e invitaciones: VIEWER no descarga esos payloads.
- [x] Denegar por defecto `X-Actor-Id` aun con UUID de un ADMIN válido cuando
      `ALLOW_LEGACY_ROLE_BOOTSTRAP=false`; probar lectura, escritura y prioridad
      de Bearer. El modo heredado solo opera con activación expresa de migración.
- [ ] Auditar todos los endpoints que devuelven datos libres o identificativos:
      configuración académica, operativa diaria, sustituciones, informes y exportaciones.
- [ ] Inventariar columnas SQL, JSON/JSONB, contenido temporal, logs, copias, archivos
      locales, IndexedDB y snapshots. Clasificar identidad, apoyo sensible y datos operativos.
- [ ] Verificar TLS, secretos, permisos de producción, backups cifrados, Resend,
      aislamiento por centro y `ALLOW_LEGACY_ROLE_BOOTSTRAP=false` realmente desplegado.

**Nota de compatibilidad:** se restringe la descarga de datos completos a VIEWER,
pero se conservan las lecturas de metadatos de cursos/escenarios. Preparar
posteriormente vistas mínimas de solo lectura en lugar de reabrir el payload completo.

## Fase 1. Minimización y separación de identidades

- Mantener IDs internos aleatorios para alumnos/profesionales y referencias
  de planificación. No usar nombres o documentos personales como IDs.
- Separar identidad, observaciones sensibles, apoyos y planificación en respuestas
  distintas. No incluir automáticamente notas libres en resultados del solver.
- Definir contratos de lectura específicos: centro + rol + grupo/servicio asignado
  + finalidad. VIEWER no adquiere acceso a identidades por pertenecer al centro.
- Añadir exportación sin identificadores como opción segura, con eliminación real
  de atributos reidentificables; no llamarla "anónima" sin verificarlo.

## Fase 2. Cifrado autenticado por centro

- Aplicar cifrado a nivel de aplicación para nombres, apellidos, notas y
  cargas JSON con datos personales; no confiar solo en cifrado de disco.
- Usar AEAD estándar (p. ej. AES-256-GCM) de una librería auditada, con nonce
  único por operación y AAD que vincule centro, tabla, fila y campo.
- Crear una DEK independiente por centro; guardar únicamente su envoltura
  cifrada con KMS externo. No persistir DEK legibles en PostgreSQL, código,
  logs, backups ni snapshots. Versionar claves y formato de ciphertext.
- Planificar rotación y restauración de claves. El fallo de KMS/descifrado debe
  impedir la lectura, sin devolver el campo cifrado como si fuera texto.
- Evaluar búsqueda exacta mediante índice ciego HMAC por centro si se necesita;
  nunca reutilizar ciphertext determinista como índice sin análisis de riesgo.
- Mantener identidades cifradas fuera del flujo de cálculo CP-SAT siempre que
  el solver pueda operar solo sobre referencias seudónimas.

## Fase 3. Migración segura de datos existentes

1. Definir esquema aditivo Alembic: columnas cifradas y versión de clave, sin
   borrar columnas legadas ni cambiar silenciosamente los JSON anteriores.
2. Ensayar backup y restauración con claves disponibles por canal separado.
3. Migrar por centro y lotes verificables; registrar progreso sin datos personales.
4. Ejecutar lecturas compatibles durante la transición, con fecha fin explícita
   y prohibición de persistir nuevos datos sensibles en claro.
5. Verificar integridad, cobertura del cifrado y recuperación autorizada.
6. Retirar columnas/JSON en claro únicamente después de aprobación, backup
   seguro y plan de reversión. Examinar también copias históricas y retención.

No ejecutar migración destructiva ni rotación de claves en producción sin
ensayo de restauración y autorización explícita.

## Fase 4. Navegadores y varios dispositivos

- Diseñar cifrado de IndexedDB por cuenta/dispositivo con Web Crypto,
  sin guardar la clave de descifrado accesible junto a la caché.
- Mostrar bloqueo/desbloqueo de trabajo local y tratamiento explícito al cerrar
  sesión, cambiar de usuario o centro. Evitar restauraciones silenciosas.
- Delimitar alcance offline, caducidad local y política para dispositivos compartidos.
  La revocación remota NO borra copias ya exportadas o dispositivos desconectados.
- Evitar incluir secretos de cuenta o claves en exportaciones JSON; ofrecer
  exportación cifrada y restauración autenticada.
- Conservar el estado previo aplicado y resolver sincronización con versiones/409,
  no con sobrescritura bidireccional implícita.

## Fase 5. Accesos detallados, sincronización y auditoría

- Comprobar permisos en cada endpoint, no solo en botones del navegador.
- Separar READ_SCHEDULE, READ_IDENTITY, READ_SUPPORT_SENSITIVE,
  EDIT_SCHEDULE, EXPORT_PERSONAL_DATA y MANAGE_MEMBERS, con denegación
  por defecto y alcance por grupo/servicio cuando corresponda.
- Completar invitaciones/roles, revocación de sesión y registros de eventos
  sin cuerpo de petición/respuesta, contraseñas, tokens ni notas.
- Añadir control de versiones a configuración, matrícula, horario y snapshots.

## Fase 6. Verificación previa al uso con datos reales

Pruebas obligatorias:
- Un volcado SQL o backup sin acceso a KMS no desvela campos protegidos.
- VIEWER no puede descargar matrícula completa ni snapshots sin filtrar.
- Un usuario de un centro no obtiene datos de otro forzando identificadores.
- Una cuenta revocada no lee datos remotos; un navegador compartido no
  expone información de otra sesión.
- Se conserva compatibilidad con JSON antiguos y modo offline controlado.
- La rotación, pérdida temporal de KMS, backup y restauración están ensayadas.
- Logs, errores, trazas, telemetría y archivos de prueba no exponen datos reales.
- CI verde en la revisión exacta; revisión de riesgos, contratos con proveedores
  y EIPD cuando proceda, antes del piloto con menores.

## Criterio operativo de avance

No llamar "protegido mediante cifrado" a un endpoint hasta verificar su ruta
completa: almacenamiento, consultas, snapshots, exportación, cache y backup.
La primera restricción de VIEWER reduce exposición, **no sustituye** el
cifrado y control granular pendientes.
