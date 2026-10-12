# Vista previa semanal CP-SAT — contrato de integración (primera iteración)

Motor: `WolcenOn/GestorEscuela`, rama `integracion-horario-pt-al`.
Frontend: `WolcenOn/Horario-PT-AL`, rama `integracion-gestor-escuela`.

## Nuevo endpoint

`POST /schools/{school_id}/weekly-timetable/preview`

- Requiere pertenecer al centro y rol **PLANNER o ADMIN** (no VIEWER).
- **No escribe** ni modifica el horario, el escenario, alumnos ni PostgreSQL.
- Trabaja con **identificadores**, no necesita ni admite nombres de alumnos,
  diagnósticos, notas PT/AL o listas de participantes.
- Entrada limitada (100 asignaturas/clase, 150 sesiones, 500 bloqueos);
  tiempo máximo de cálculo: 15 segundos.
- CP-SAT respeta restricciones duras: ningún solapamiento de docente o
  grupo de clase, carga semanal exacta por materia, duración exacta de cada
  sesión, días admitidos, disponibilidad horaria, bloqueos y máximo diario.
- Nuevo atributo opcional `supports`: demandas PT/AL individuales pendientes,
  con el total semanal **restante** y duraciones ya particionadas. No programa
  apoyos adicionales para grupos de alumnos mixtos con objetivos diferentes.
- Cada apoyo lleva `pupil_token`, UUID aleatorio **por petición**, compartido
  únicamente entre PT y AL de ese alumno en ese cálculo. No se mandan los IDs
  originales ni nombres de alumnos. El backend no incluye este token en la
  respuesta; devuelve solo el `request_id` y el horario propuesto.
- El motor bloquea dos apoyos simultáneos del mismo alumno, dos clases/apoyos
  del mismo profesional y extracciones durante materias presentes en
  `blocked_subjects`. Las asignaturas restantes permiten extracción parcial.
- Las preferencias de día se optimizan pero **no** se vuelven bloqueos.
- Estados: `feasible` (propuesta), `infeasible` (se demostró incompatible)
  y `unknown` (límite de búsqueda u otro estado no concluyente).
- La respuesta contiene `preview_only: true` para impedir interpretarla
  como horario confirmado.

### Ejemplo mínimo

```json
{
  "start_time": "09:00",
  "end_time": "12:00",
  "max_time_seconds": 5,
  "lessons": [
    {
      "group_id": "1A",
      "subject_id": "MAT",
      "teacher_id": "P1",
      "weekly_minutes": 105,
      "durations": [45, 60],
      "allowed_days": [0, 1, 2],
      "preferred_days": [1],
      "max_sessions_per_day": 1
    },
    {
      "group_id": "2A",
      "subject_id": "MAT",
      "teacher_id": "P1",
      "weekly_minutes": 180,
      "durations": [90, 90],
      "max_sessions_per_day": 1
    }
  ],
  "busy": [
    {
      "weekday": 0,
      "start_time": "09:00",
      "end_time": "10:00",
      "teacher_id": "P1"
    }
  ]
}
```

`durations` es la **partición calculada previamente por el frontend** a
partir de `subjectPatterns[course][subject]`, o por otro sistema fiable.
El backend **verifica** que la suma coincide con `weekly_minutes`, pero aún
no infiere ni reoptimiza los tamaños de las sesiones. Por ejemplo, Matemáticas
de 1.º puede solicitar [45, 60] y Matemáticas de 2.º [90, 90].

Los bloqueos de profesor se aplican también a sesiones PT/AL existentes.
Los de grupo se reservan para la actividad que ocupa la clase completa
(p. ej. recreo), no para una extracción parcial PT/AL.

## Apoyos PT/AL compartidos en grupos ya existentes

Nueva propiedad opcional `group_supports` del mismo POST. El frontend
puede utilizar grupos de apoyo que el centro ya ha definido **o generar
agrupaciones virtuales temporales**, sin guardar nuevos grupos en el centro.
En ambos casos calcula el déficit individual descontando sesiones previas.

```json
{
  "request_id": "group-support-1",
  "service": "PT",
  "teacher_id": "teacher-pt",
  "session_minutes": 45,
  "participants": [
    {
      "pupil_token": "token-aleatorio-de-esta-peticion-a",
      "group_id": "1A",
      "weekly_minutes": 90,
      "blocked_subjects": ["Lengua"],
      "avoided_subjects": ["Matemáticas"],
      "preferred_subjects": []
    },
    {
      "pupil_token": "token-aleatorio-de-esta-peticion-b",
      "group_id": "1A",
      "weekly_minutes": 45,
      "blocked_subjects": [],
      "avoided_subjects": [],
      "preferred_subjects": ["Matemáticas"]
    }
  ],
  "allowed_days": [0, 1, 2, 3, 4],
  "max_sessions_per_day": 2
}
```

Se proponen dos sesiones PT de 45 minutos: el primer alumno participa en
ambas y el segundo solo en una. **No se le atribuyen 90 minutos al segundo.**
Los asistentes pueden variar por sesión y no se devuelve su identidad:
`group_supports` en la respuesta indica franja, servicio y número de
participantes, pero **nunca** los tokens anónimos.

Para cada alumno, `blocked_subjects` impide extraer de esa asignatura,
`avoided_subjects` penaliza coincidencias y `preferred_subjects` las
premia. Ninguna preferencia blanda puede saltarse una prohibición o un
solapamiento de alumnado/profesor.

El piloto admite 8 participantes por solicitud grupal, objetivos divisibles
entre la duración común, máximo 20 sesiones por grupo y 150 sesiones en la
propuesta total. Grupos que no cumplen estas condiciones siguen pendientes
de ajuste manual. Las sesiones existentes se descuentan por alumno,
considerando `excludedStudentIds` en la configuración local.

### Propuestas automáticas conservadoras (frontend)

`Horario-PT-AL/js/auto-support-groups.js` propone combinar **asignaciones
PT/AL individuales existentes** cuando comparten profesional, servicio,
curso y prohibiciones de extracción compatibles. **Pueden proceder
de diferentes clases del mismo curso**: el motor comprueba las restricciones
de extracción de cada alumno contra las materias de su propia clase. Respeta
las preferencias blandas de cada alumno y descuenta los apoyos programados.

- Elige duraciones comunes de 45, 30 o 15 minutos, sin exceder los objetivos
  individuales; máximo ocho participantes y diez sesiones semanales por
  agrupación automática (dos al día de lunes a viernes).
- Los alumnos sin profesional asignado, de **distintos cursos**, o con
  prohibiciones de extracción incompatibles **no se agrupan** de momento.
  Los alumnos de diferentes clases del mismo curso sí pueden coincidir si
  tienen el mismo profesional y se satisfacen sus reglas individuales.
- La petición utiliza los mismos tokens efímeros y no transmite nombres,
  diagnósticos ni IDs originales de estudiantes.
- Si la propuesta agrupada resulta `infeasible`, el cliente realiza una
  **segunda vista previa con las sesiones individuales**. El resultado visible
  corresponde a esa segunda simulación, que puede ser `feasible`,
  `infeasible` o `unknown`. No se presenta un fracaso de agrupación opcional
  como prueba de inviabilidad de todo el horario.
- **No se guarda ni se aplica automáticamente ningún grupo**. Es un piloto
  no destructivo, pendiente de interfaz de aceptación, definición de
  espacios compartidos y formación desde alumnado sin asignaciones previas.

### Diagnósticos explicables de inviabilidad

Si CP-SAT **demuestra** que una propuesta semanal es inviable, el backend
puede añadir causas concretas en `reasons`, calculadas únicamente a partir
de restricciones duras comprobables:

- carga de una materia superior a los minutos disponibles de su profesor o
  grupo en los días/franjas permitidos;
- carga total de un especialista (docencia, PT y AL) mayor que su capacidad
  libre semanal;
- exceso de minutos curriculares de una clase respecto a su jornada;
- solapamiento de bloqueos fijos ya presentes para un profesor o clase.

Nunca se incluyen tokens de alumnos ni diagnósticos clínicos en las razones.
**La ausencia de una razón concreta no implica que exista una solución**:
un conflicto puede depender de combinaciones entre muchas restricciones.
El estado `unknown` significa búsqueda inconclusa, no inviabilidad demostrada.

## Aulas compartidas y especialistas itinerantes

La vista previa acepta restricciones **opcionales** de recursos y trayectos:

- `travel_minutes` en el cuerpo principal (0, 15, 30, 45 o 60).
  Predeterminado **0** para preservar configuraciones antiguas.
- `location_id` en una materia, apoyo PT/AL, grupo de apoyo o bloqueo fijo.
  Se usa únicamente para verificar traslados de un mismo profesional.
  Cuando dos actividades consecutivas tienen *ubicaciones conocidas y
  distintas*, el motor exige el intervalo completo de traslado entre ellas.
  No estima distancias geográficas ni diferencia trayectos por dirección.
- `room_id` en esas actividades: **dos actividades no pueden ocupar la
  misma sala explícita al mismo tiempo**, aunque tengan profesores distintos.
  También se aceptan bloqueos con solo `room_id`, para reservar una sala
  sin identificar personal ni alumnos.
- Cuando la ubicación no se proporciona, no se inventa y el motor
  **no aplica** desplazamiento hacia o desde esa actividad. `room_id` por
  sí solo tampoco crea una ubicación para cálculos de viaje.
- Las duraciones y los traslados usan una rejilla de 15 minutos. Una
  actividad en la misma ubicación no necesita margen adicional; un cambio
  de ubicación en actividades del mismo profesor sí.

`Horario-PT-AL` incorpora en «Planificación del centro → Parámetros de
generación global» el tiempo opcional de traslado y la sala PT/AL compartida.
Cuando se activa el traslado, los identificadores de clase se emplean como
**ubicaciones diferenciadas de aula**, no como distancias reales. Cuando
se indica una única sala de apoyo, **todos los apoyos y sus sesiones ya
programadas** enviados a esta vista previa se consideran ocupantes
exclusivos de esa sala. Sin sala configurada, no se presupone cuál utilizan.

No existe todavía optimización de rutas entre edificios, aforo de salas
de más de una sesión ni sala individual por alumno. La propuesta es siempre
informativa y no modifica configuración académica ni base de datos.

## Límites explícitos antes de producción

1. **No** distribuye por sí solo la carga curricular a distintas duraciones:
   recibe una lista de sesiones ya calculada.
2. **Sí** propone ahora el déficit semanal de apoyos **individuales**
   de un solo alumno, siempre que su grupo PT/AL sea único, se disponga de
   objetivo de minutos y exista profesor compatible. Descuenta los minutos
   ya programados y respeta bloqueos explícitos `no-salir` y materias
   cuya extracción esté prohibida. **No** genera todavía sesiones
   de creación persistente de grupos, agrupaciones entre diferentes
   cursos/docentes, divisiones arbitrarias entre distintos tamaños de sesión
   o tolerancias de exceso. Existen **propuestas virtuales conservadoras**
   a partir de asignaciones individuales, sin modificar datos. Sí se optimizan
   las preferencias blandas de extracción por materia para los grupos
   ya configurados cuando cumplen las condiciones del piloto. Cuando se omiten
   necesidades incompatibles se debe avisar.
3. **No** resuelve la planificación de actividades del centro que aún no
   tienen franja concreta, ni recursos compartidos, desplazamientos o
   reuniones/funciones sin asignación temporal. El frontend sí puede enviar
   bloqueos de actividades *ya programadas*.
4. **No** aplica cambios a los horarios actuales. Los resultados permanecen
   como texto informativo en la vista Cuenta y sincronización.
5. Las disponibilidades y recreos se derivan del estado local; no se
   consulta ni guarda información sobre menores en el backend.
6. La rejilla provisional exige múltiplos de 15 minutos. Las franjas
   tradicionales sin horario explícito siguen funcionando por separado.
7. Los límites conjuntos de 150 sesiones y 100 demandas entre materias
   y apoyos convierten esto en una validación piloto de alcance acotado,
   no en un motor capaz de planificar todo un colegio.
8. Los tokens anónimos de alumnos se generan en cada petición por el navegador
   mediante una fuente criptográfica. No sustituyen el cifrado de los datos
   reales del proyecto o de IndexedDB ni justifican almacenar las demandas.

## Siguientes etapas

- Contrato versionado de restricciones y sesionado por curso/clase/profesor,
  con herencia configurable de duraciones permitidas.
- Cargas semanales y fraccionamiento optimizados conjuntamente por CP-SAT.
- Agenda única de especialistas, salas, turnos, desplazamientos y
  coordinación entre centros.
- PT/AL por alumno con identidad pseudonimizada, objetivos, preferencias
  de extracción, no solapamiento individual, permisos y cifrado.
- Guardado opcional de propuestas con control de versiones y confirmación
  explícita, sin destruir horarios existentes.
