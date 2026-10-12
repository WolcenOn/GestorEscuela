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
- `travel_rules` en el cuerpo: hasta 100 rutas **dirigidas** con
  `from_location_id`, `to_location_id` y `minutes`. Una ruta A→B
  puede exigir 15 minutos y B→A exigir 30; el tiempo específico tiene
  prioridad sobre `travel_minutes`. Los sentidos no configurados utilizan
  el margen general. Se validan ubicaciones distintas, duraciones en
  pasos de 15 y ausencia de rutas duplicadas para el mismo sentido.
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
generación global» el tiempo general opcional, las rutas por sentido y la
sala PT/AL compartida.
Cuando se activa el traslado, los identificadores de clase se emplean como
**ubicaciones diferenciadas de aula**, no como distancias reales. Cuando
se indica una única sala de apoyo, **todos los apoyos y sus sesiones ya
programadas** enviados a esta vista previa se consideran ocupantes
exclusivos de esa sala. Sin sala configurada, no se presupone cuál utilizan.

Las salas se resuelven por prioridad desde Horario-PT-AL:
**aula de la sesión existente > sala del grupo PT/AL > sala habitual del
profesional > sala global**. Grupos virtuales con distintas salas obligatorias
no se combinan automáticamente. Cada sala resuelta se transmite como
`room_id` y como `location_id` de tipo `room:...`. Las ubicaciones de
clase se transmiten con el prefijo `class:...` si existe un tiempo general
o al menos una ruta específica. Solo estas ubicaciones explícitas participan
en el cálculo de trayectos.

No existe todavía optimización de rutas entre edificios, aforo de salas
de más de una sesión ni sala individual por alumno. La propuesta es siempre
informativa y no modifica configuración académica ni base de datos.

### Asignación automática de salas en apoyos PT/AL (opcional)

Una necesidad individual de `supports` o grupal de `group_supports`
puede incluir **`room_candidates`**: entre una y ocho referencias a
salas que aparecen en `rooms`. La sala no se fija por petición;
**el motor elige una sala por cada sesión**, teniendo en cuenta horarios
de apertura, plazas simultáneas, reservas previas y desplazamientos
del especialista. Las diferentes sesiones de un mismo grupo pueden
acabar en salas distintas si así se satisfacen mejor las restricciones.

```json
{
  "room_candidates": ["Sala PT", "Sala de apoyo compartido"]
}
```

No se admiten salas repetidas, inexistentes, ni la combinación de
`room_candidates` con `room_id` o `location_id` obligatorios.
La respuesta de cada apoyo incluye `room_id` con la sala realmente
elegida, sin devolver nombres, identificadores o tokens del alumnado.
Si no se proporcionan candidatos, se conserva la asignación de sala
explícita y todo el comportamiento legado de uso exclusivo.

La opción de selección automática se habilita **explícitamente** en
Horario-PT-AL. Nunca mueve sesiones existentes ni anula una sala fijada
en el grupo o en el profesional. La sala general se mantiene como
predeterminada cuando la selección automática no está habilitada.

### Equipamiento y accesibilidad de la sala (políticas de actividad)

`rooms[].features` permite enumerar únicamente estas características
**genéricas del entorno físico**, sin comentarios libres ni datos médicos:

- `acceso_sin_escalones` — ruta accesible sin escalones;
- `mesa_regulable` — mobiliario regulable;
- `aislamiento_acustico` — aislamiento acústico;
- `material_logopedico` — material disponible para intervención AL;
- `pizarra_digital` — pantalla o pizarra digital.

Los apoyos `supports[]` y `group_supports[]` pueden exigir
`required_features` con cualquiera de esas características, sin duplicados.
Estas reglas pertenecen **al servicio o actividad**, nunca se extraen
de diagnósticos ni expedientes de alumnos. El motor no devuelve tokens,
identificadores de alumnado ni los requisitos en su respuesta.

Si hay `room_candidates`, solo se consideran las salas configuradas
que dispongan de **todas** las características obligatorias. Si ninguna
cumple, el resultado es `infeasible`: no se relaja ninguna condición.
Una sala fija también debe estar inventariada y cumplirlas; si falta
su definición, la petición se rechaza como configuración incompleta
(HTTP 422). Si tiene definición pero carece de las características,
la simulación indica inviabilidad. Sin requisitos declarados el
comportamiento anterior permanece intacto.

Ejemplo sin información personal:

```json
{
  "rooms": [
    {
      "room_id": "Sala AL",
      "capacity": 3,
      "features": ["aislamiento_acustico", "material_logopedico"]
    }
  ],
  "group_supports": [{
    "request_id": "sesiones-AL",
    "service": "AL",
    "room_candidates": ["Sala AL"],
    "required_features": ["material_logopedico"]
  }]
}
```

El fragmento ilustra los nuevos campos y no es por sí solo una petición
completa; las necesidades PT/AL incluyen los demás campos obligatorios.
El frontend permite marcar requisitos generales para PT y AL, no
requisitos asociados a un alumno individual.

### Aforo y disponibilidad por día y hora (vistas previas)

La propiedad opcional `rooms` del POST admite hasta 50 salas configuradas:

```json
{
  "rooms": [
    {
      "room_id": "Sala PT 1",
      "capacity": 2,
      "windows": [
        {"weekday": 0, "start_time": "09:00", "end_time": "11:00"},
        {"weekday": 2, "start_time": "10:00", "end_time": "12:00"}
      ]
    },
    {
      "room_id": "Sala de apoyo compartido",
      "capacity": 4,
      "windows": []
    }
  ]
}
```

- `capacity` es el aforo simultáneo en **alumnos presentes**, entre 1 y 30.
  Cada sesión PT/AL individual consume 1 plaza; un grupo utiliza tantas
  plazas como alumnos tengan asistencia **a esa sesión**, aunque sus objetivos
  semanales sean distintos. El motor puede permitir distintos profesionales
  en una sala si la suma de participantes cabe en ella.
- En una sala **sin especificación** en `rooms` se mantiene el comportamiento
  anterior: **una única sesión simultánea**, sin contar los alumnos de dentro.
  Esto evita invalidar los proyectos que no han indicado aforos.
- Las clases ordinarias que reserven `room_id` ocupan toda su sala
  configurada. Los bloqueos fijos solo con `room_id`, sin `room_units`,
  también reservan su capacidad completa.
- Un bloqueo fijo de una sesión PT/AL puede indicar `room_units` (1–30),
  que representa sus asistentes reales: cuenta solamente esas plazas.
- `windows: []` no añade límites horarios. Si se indican una o más franjas,
  **únicamente esos días y horas están abiertos**; los días omitidos se
  consideran cerrados. Franjas en pasos de 15 minutos, sin solapamientos,
  dentro de la jornada de la petición. Máximo 30 por sala y 200 en total.
- Las reservas cerradas ocupan el aforo completo. Ninguna actividad con
  `room_id` configurado puede solaparse con un periodo de cierre, aunque
  haya plazas libres durante la jornada abierta.
- No se envían nombres ni identificadores reales de alumnos para calcular
  aforos. La propuesta no se aplica ni se guarda.

En Horario-PT-AL se configuran los aforos y horarios en **Centro →
Planificación del centro → Parámetros de generación global**, con una línea
`Sala | 4` para mantenerla disponible toda la jornada, o varias líneas
`Sala | 4 | lunes | 09:00 | 12:00` para su disponibilidad concreta.
Las salas que no se enumeran siguen teniendo uso exclusivo.

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
   tienen franja concreta, ni rutas físicas entre edificios, asignación
   automática de espacios o reuniones/funciones sin asignación temporal.
   **Sí** impone exclusividad de salas indicadas explícitamente y un margen
   opcional de traslado entre ubicaciones conocidas. El frontend puede enviar
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
