# GestorEscuela: motor semanal del centro, especialistas y PT/AL

**Repositorio del motor:** `WolcenOn/GestorEscuela`, rama `integracion-horario-pt-al`.
**Frontend:** `WolcenOn/Horario-PT-AL`, rama `integracion-gestor-escuela`.
Gestor-Alimentacion es otro proyecto y no participa en esta integración.

## Estado verificado en octubre de 2026

- `solver/optimizer.py`: OR-Tools CP-SAT para **sustituciones de un día**.
- `solver/weekly.py`: ejecuta los problemas diarios en secuencia y mantiene
  las estadísticas de equidad; **no construye todavía el horario semanal de
  todas las materias simultáneamente**.
- `api/academic.py`: importa actividad ordinaria ya asociada a
  `weekday`, `slot_id`, profesor, grupo, especialidad. Los tramos solo
  tienen `id`, `label` y `order`; todavía no modelan duraciones ni
  intervalos reales en el backend.
- `Horario-PT-AL/js/center-planning.js`, `time-patterns.js` y
  `global-scheduler.js`: disponen de duración general y reglas
  de duración mínima/preferida/máxima **por curso y materia**, rejilla 15 min
  y algunas validaciones de especialistas/PT-AL.
- Las fechas/intervalos escolares reales, carga curricular por curso,
  políticas particulares por clase, disponibilidad cruzada e identidad de
  alumnado PT/AL aún necesitan un contrato explícito compartido.
- El motor de sustituciones protege un docente único por `slot_id`, pero
  eso por sí solo NO detecta solapes parciales de intervalos de diferente
  duración ni resuelve restricciones conjuntas de toda la semana.

## Fase A — Validación de entrada y contrato horario

- [x] Rechazar dos actividades de un mismo docente en mismo día/tramo de
  `academic-configuration`, incluido `weekday=null` (actividad semanal).
- [x] Rechazar duplicidades de profesor/tramo en la entrada directa al
  motor de sustituciones para evitar sobrescrituras en diccionarios.
- [x] Añadir pruebas de actividad de especialista en dos aulas a la vez.
- [x] Añadir intervalos reales opcionales `start_time/end_time` en
  `academic-configuration`, con migración Alembic 0018 y rejilla de
  15 minutos, hasta 180 minutos por bloque. `slot_id` legado funciona
  sin horas inferidas.
- [x] Rechazar solapes parciales del mismo docente en cualquier actividad,
  y del mismo grupo en dos clases ordinarias. Una extracción PT/AL puede
  coincidir con la clase del grupo sin implicar que coincida todo el alumnado;
  la colisión por alumno queda pendiente de modelar.
  Se distinguen días y sesiones adyacentes.
- [x] El motor de sustituciones considera intervalos solapados al escoger
  profesionales y al impedir dos coberturas coincidentes.
- [ ] Extender el modelo más allá de bloques predefinidos: currículo semanal,
  partición variable de materias, asignación automática de docentes/aulas.
- [ ] Clasificar restricciones como duras o preferencias; explicar
  por qué un horario solicitado resulta incompatible.

## Fase B — Duraciones flexibles y herencia sin duplicación

Ámbitos, de mayor a menor generalidad:

`Centro → etapa/curso → asignatura por curso → clase concreta → docente/asignación`

- Duración global habitual, por ejemplo 45 min.
- Matemáticas 1.º: preferir 60 min, permitir 45/60 min.
- Matemáticas 2.º: permitir 90 min; si es obligatorio,
  fijar 90 como tamaño único admisible.
- Bloques específicos de 30/45/60/75/90/120 min donde el centro lo autorice.
- Días máximos/mínimos, separación, bloques dobles y tiempos
  de descanso por asignatura/docente.
- La suma semanal de cada asignatura debe cumplir exactamente
  los minutos curriculares salvo tolerancia explícita del centro.
- Mantener `lessonMinutes` y `subjectPatterns` del frontend en
  las importaciones/exportaciones existentes; migraciones aditivas.

## Fase C — Especialistas y recursos

- Unificar agenda semanal de profesores ordinarios, especialistas, PT y AL.
- Solape de **intervalos** y no solo igualdad de `slot_id`.
- Respetar horas de entrada/salida, reuniones, no lectivas,
  reducciones, apoyos, espacios compartidos y jornadas en otros centros.
- Desplazamientos entre pabellones/aulas cuando existan restricciones.
- Sesiones agrupadas o compartidas: modelarlas explícitamente
  como una sola actividad con varias clases si realmente corresponden
  al mismo espacio y profesional (nunca deducirlas de duplicidades).
- Priorizar las asignaciones de especialistas con menor flexibilidad
  y explicar los cuellos de botella sin mostrar datos personales innecesarios.

## Fase D — PT/AL y horario ordinario en una misma optimización

- Generar sesiones de apoyo desde necesidades y objetivos semanales de
  cada alumno, sin exigir plantillas manuales.
- Sesiones con duración preferida y límites; p. ej. 45 preferidos,
  30/60 alternativas y sin exceso de minutos por alumno.
- Respetar política de extracción por materia, recreos, coordinaciones,
  disponibilidad del profesional y coincidencia del alumno en otros apoyos.
- Los grupos con alumnado de necesidades distintas exigen participación
  por sesión explícita; no completar horas a menores que no lo requieren.
- Resolver simultáneamente clases, docentes, recursos y apoyos, o usar
  etapas reparables con garantía de restricciones duras.

## Fase E — Solver, UX y controles de seguridad

- Propuestas **no destructivas**: calcular, explicar, revisar, aplicar;
  los cambios manuales pueden quedar bloqueados para el siguiente cálculo.
- OR-Tools CP-SAT con límites de tiempo, distinción entre inviable y
  búsqueda sin solución conocida, objetivos priorizados y pruebas reproducibles.
- Permisos por centro/usuario/rol, mínimos datos por petición, snapshots
  sin lectura identificativa para VIEWER, cifrado y claves separadas según
  `docs/PRIVACY_ENCRYPTION_ROADMAP.md`.
- Sincronización multidispositivo versionada para evitar pérdida de cambios.
- Compatibilidad con modo offline e importación JSON legado.

## Escenarios de aceptación

1. La misma materia admite bloques distintos entre 1.º y 2.º sin cambiar la
   duración semanal y sin residuos no permitidos.
2. Un especialista que imparte en 1.º A no aparece en 2.º B
   durante intervalos solapados ni durante traslado obligatorio.
3. Una sesión PT/AL no duplica un profesional ni un alumno.
4. El motor detecta un conflicto de duración, especialidad,
   disponibilidad, aula o extracción con explicación específica.
5. La imposibilidad de cumplir una regla dura no se disfraza
   incumpliéndola: se informa al centro y se ofrecen alternativas.
6. Nunca se aplica una propuesta ni se reescribe el horario anterior
   hasta que el usuario la confirme expresamente.


## Entrega de intervalos explícitos: comportamiento y límites

Una franja puede declararse, por ejemplo, como:

```json
{"id": "MAT-2-90", "label": "Matemáticas 2º", "order": 2,
 "start_time": "09:00", "end_time": "10:30"}
```

Los dos atributos temporales son opcionales **en conjunto** para preservar
los datos heredados. Deben cumplir `HH:mm`, inicio anterior a fin, rejilla
de 15 minutos y duración máxima de 180 minutos. Nunca se convierte
automáticamente una etiqueta «09:00» o un número de orden en una duración.

Si dos franjas explícitas se cruzan, compartir docente, grupo o sustituto
produce un conflicto obligatorio. Si una de ellas es antigua y no tiene horas,
solo podemos detectar el conflicto por igualdad de `slot_id`; por seguridad
operativa conviene completar las horas antes de generar calendarios que
mezclen duraciones distintas. Este bloque no implementa aún:
- edición de duraciones por clase en el backend ni la partición automática
  de las horas semanales;
- conflictos entre alumnos de PT/AL y apoyos sin grupos explícitos;
- desplazamientos entre centros, aulas y recursos comunes;
- propuesta semanal integrada con duración variable (el motor semanal
  actual continúa dedicado a sustituciones por día).

La migración es **aditiva** y reversible, pero eliminar columnas de horarios
reales con el downgrade causaría pérdida de esas horas: practicar backups y
restauración antes de revertirla. No se ha migrado una base real desde esta rama.
