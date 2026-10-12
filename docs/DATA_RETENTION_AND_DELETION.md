# Política técnica de retención, eliminación y anonimización

Estado: propuesta operativa de Fase 0.4. Este documento define el comportamiento técnico del producto; no sustituye la validación jurídica ni las instrucciones del responsable del tratamiento de cada centro.

## Principios

1. **Minimización.** GestorEscuela conserva únicamente los datos necesarios para planificación, operativa, seguridad y trazabilidad. El log de auditoría no almacena cuerpos de peticiones ni respuestas.
2. **Aislamiento por centro.** Los datos académicos y operativos se eliminan o exportan siempre dentro del `school_id` correspondiente. Una operación sobre un centro no debe afectar a otro.
3. **Separación de cuenta y centro.** Una cuenta puede pertenecer a varios centros. Borrar una membresía no equivale a borrar la cuenta; borrar una cuenta no debe borrar automáticamente un centro compartido.
4. **Acciones destructivas explícitas.** No se realizará borrado irreversible desde una navegación ordinaria. Debe existir confirmación, autorización ADMIN, auditoría y, cuando corresponda, exportación previa.
5. **No reutilizar auditoría como copia de datos.** Los eventos contienen identificadores técnicos, actor, tipo de evento, ruta, resultado y fecha; nunca nombres de alumnado, diagnósticos, contraseñas, tokens o cuerpos JSON.

## Categorías y retención técnica

Los siguientes valores son **predeterminados técnicos propuestos**, configurables y pendientes de validación jurídica/organizativa antes de un piloto con datos reales:

| Categoría | Retención técnica propuesta | Eliminación |
| --- | --- | --- |
| Sesiones revocadas o caducadas | 30 días | Purga periódica |
| Tokens de recuperación usados/caducados | 7 días | Purga periódica |
| Contadores de throttling de login inactivos | 24 horas | Purga periódica |
| Invitaciones aceptadas o caducadas | 90 días | Purga periódica |
| Auditoría de seguridad y cambios | 12 meses | Purga por antigüedad, salvo conservación requerida por el centro |
| Escenarios borrador | Hasta borrado explícito o política del centro | Eliminación por centro/curso |
| Horarios publicados y operativa | Según política del centro y curso académico | Archivo o eliminación controlada |
| Datos de alumnado/profesorado | Mientras sean necesarios para el centro/curso | Eliminación o anonimización controlada |

No se debe implementar una purga automática de datos académicos con estos plazos hasta que la política haya sido validada para el despliegue real.

## Eliminación de un centro

La futura operación de eliminación de centro debe exigir:

- sesión Bearer activa y rol `ADMIN` del centro;
- confirmación reforzada que incluya el nombre del centro;
- comprobación de que no se está actuando sobre otro tenant;
- recomendación de exportación/backup previa;
- revocación de sesiones o accesos que queden sin membresías válidas cuando proceda;
- eliminación en cascada de datos exclusivos del centro;
- conservación únicamente de la mínima auditoría necesaria, preferiblemente anonimizada cuando deje de ser necesario conservar el `actor_user_id`;
- evento semántico de auditoría de la solicitud y resultado sin copiar datos académicos.

No se expone todavía un endpoint destructivo de borrado de centro en Fase 0.4: se documenta primero el contrato para evitar introducir una operación irreversible sin backup/restauración probado, que pertenece al gate operativo de Fase 0.5.

## Eliminación de cuenta

Una cuenta no podrá eliminarse mientras sea el único `ADMIN` de un centro. Antes será necesario transferir administración o eliminar el centro mediante su flujo específico. Si la cuenta mantiene otras membresías, deben revocarse de forma explícita.

Al eliminar una cuenta se eliminarán credenciales, sesiones y tokens de recuperación. Los registros de auditoría históricos no conservarán correo, nombre ni otros datos de perfil; la política de anonimización del identificador técnico se aplicará cuando ya no exista una necesidad legítima de atribución.

## Anonimización académica

Cuando el centro necesite conservar estadísticas o evidencia operativa sin identidad directa, la anonimización debe producir un nuevo conjunto de datos sin nombres, correos, identificadores externos ni campos libres. No se considerará anonimización suficiente sustituir únicamente el nombre por un UUID si el resto de atributos permite reidentificar fácilmente a la persona.

## Auditoría semántica

Los eventos críticos utilizan etiquetas estables como:

- `auth.password.change`
- `auth.password.reset_request`
- `auth.password.reset_confirm`
- `auth.session.revoke`
- `auth.logout_all`
- `membership.update`
- `membership.invitation.create`
- `membership.invitation.accept`
- `academic.configuration.replace`
- `planning.scenario.snapshot.save`
- `operations.day_plan.solve`

Los eventos no contienen el payload de la operación. El historial de centro se consulta por `school_id`; los eventos propios de cuenta se consultan separadamente por el usuario autenticado.

## Trabajo pendiente para Fase 0.5

Antes de habilitar eliminaciones irreversibles con datos reales deben existir y probarse:

1. backup PostgreSQL reproducible;
2. restauración ensayada y documentada;
3. política definitiva de retención aprobada para el despliegue;
4. tareas de purga idempotentes con modo `dry-run`;
5. checklist de exportación, eliminación y verificación posterior;
6. pruebas multi-tenant que demuestren que una purga nunca cruza `school_id`.
