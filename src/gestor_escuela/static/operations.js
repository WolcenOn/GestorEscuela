(() => {
  const nav = document.getElementById("nav");
  const pages = document.getElementById("appPages");
  if (!nav || !pages) return;

  const recessButton = document.createElement("button");
  recessButton.dataset.page = "recess";
  recessButton.textContent = "Recreos";
  nav.append(recessButton);

  const activitiesButton = document.createElement("button");
  activitiesButton.dataset.page = "activities";
  activitiesButton.textContent = "Actividades";
  nav.append(activitiesButton);

  pages.insertAdjacentHTML(
    "beforeend",
    `
    <section id="page-recess" class="page">
      <div class="page-head"><div><h2>Recreos</h2><p>Organiza turnos de vigilancia y cuántas personas necesita cada zona.</p></div></div>
      <div class="card">
        <div class="form-row">
          <label>ID<input id="recessId" placeholder="PATIO-LUN" /></label>
          <label>Turno<input id="recessLabel" placeholder="Patio principal" /></label>
          <label>Día<select id="recessDay"><option value="0">Lunes</option><option value="1">Martes</option><option value="2">Miércoles</option><option value="3">Jueves</option><option value="4">Viernes</option></select></label>
          <label>Inicio<input id="recessStart" type="time" value="11:00" /></label>
          <label>Fin<input id="recessEnd" type="time" value="11:30" /></label>
          <label>Personas necesarias<input id="recessStaff" type="number" min="1" value="2" /></label>
        </div>
        <div class="grid two" style="margin-top:12px">
          <label>Lugar<input id="recessLocation" placeholder="Patio principal" /></label>
          <label>Notas<input id="recessNotes" placeholder="Zona, indicaciones, observaciones..." /></label>
        </div>
        <div style="margin-top:12px"><strong style="font-size:12px">Docentes asignados</strong><div id="recessTeachers" class="slot-checks" style="margin-top:8px"></div></div>
        <div class="actions" style="margin-top:14px"><button class="btn primary" id="saveRecessBtn">Añadir / actualizar turno</button><button class="btn" id="saveOperationsBtn">Guardar recreos y actividades</button></div>
        <div id="operationsStatus" class="status">Los cambios se guardan conjuntamente para el centro.</div>
      </div>
      <div class="card" style="margin-top:14px"><table><thead><tr><th>Día</th><th>Turno</th><th>Horario</th><th>Personal</th><th>Asignados</th><th></th></tr></thead><tbody id="recessBody"></tbody></table></div>
    </section>

    <section id="page-activities" class="page">
      <div class="page-head"><div><h2>Actividades</h2><p>Agenda biblioteca, coordinaciones, reuniones, eventos y otras necesidades de personal.</p></div></div>
      <div class="card">
        <div class="form-row">
          <label>ID<input id="operationId" placeholder="BIBLIO-LUN" /></label>
          <label>Nombre<input id="operationLabel" placeholder="Biblioteca" /></label>
          <label>Categoría<select id="operationCategory"><option>BIBLIOTECA</option><option>COORDINACION</option><option>EVENTO</option><option>REUNION</option><option>ACOMPANAMIENTO</option><option>OTRA</option></select></label>
          <label>Tipo<select id="operationScheduleType"><option value="weekly">Semanal</option><option value="date">Fecha concreta</option></select></label>
          <label id="operationDayWrap">Día<select id="operationDay"><option value="0">Lunes</option><option value="1">Martes</option><option value="2">Miércoles</option><option value="3">Jueves</option><option value="4">Viernes</option></select></label>
          <label id="operationDateWrap" class="hidden">Fecha<input id="operationDate" type="date" /></label>
        </div>
        <div class="form-row" style="margin-top:12px">
          <label>Inicio<input id="operationStart" type="time" value="12:30" /></label>
          <label>Fin<input id="operationEnd" type="time" value="13:15" /></label>
          <label>Personas necesarias<input id="operationStaff" type="number" min="1" value="1" /></label>
          <label>Lugar<input id="operationLocation" placeholder="Biblioteca" /></label>
          <label><span>Movible</span><input id="operationMovable" type="checkbox" checked /></label>
          <label><span>Cancelable</span><input id="operationCancelable" type="checkbox" checked /></label>
        </div>
        <label style="margin-top:12px">Notas<input id="operationNotes" placeholder="Descripción o instrucciones" /></label>
        <div style="margin-top:12px"><strong style="font-size:12px">Docentes asignados</strong><div id="operationTeachers" class="slot-checks" style="margin-top:8px"></div></div>
        <div class="actions" style="margin-top:14px"><button class="btn primary" id="saveActivityBtn">Añadir / actualizar actividad</button><button class="btn" id="saveOperationsBtn2">Guardar recreos y actividades</button></div>
      </div>
      <div class="card" style="margin-top:14px"><table><thead><tr><th>Actividad</th><th>Cuándo</th><th>Horario</th><th>Personal</th><th>Asignados</th><th></th></tr></thead><tbody id="operationsBody"></tbody></table></div>
    </section>`,
  );

  let operations = {recess_shifts: [], scheduled_activities: []};
  const dayNames = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"];

  function teacherChecks(containerId, selected = []) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = config.teachers
      .map((teacher) => {
        const checked = selected.includes(teacher.id) ? "checked" : "";
        return `<label><input type="checkbox" value="${esc(teacher.id)}" ${checked}>${esc(teacher.display_name || teacher.id)}</label>`;
      })
      .join("");
  }

  function selectedTeachers(containerId) {
    return [...document.querySelectorAll(`#${containerId} input:checked`)].map((item) => item.value);
  }

  function renderOperations() {
    teacherChecks("recessTeachers");
    teacherChecks("operationTeachers");
    const recessBody = document.getElementById("recessBody");
    recessBody.innerHTML = operations.recess_shifts
      .map((item) => `<tr><td>${dayNames[item.weekday]}</td><td><strong>${esc(item.label)}</strong><br><span class="muted">${esc(item.location || "—")}</span></td><td>${item.start_time}–${item.end_time}</td><td>${item.assigned_teacher_ids.length}/${item.required_staff}</td><td>${esc(item.assigned_teacher_ids.map(teacherName).join(", ") || "Sin asignar")}</td><td><button class="btn small danger" data-remove-recess="${esc(item.id)}">Eliminar</button></td></tr>`)
      .join("");

    const activitiesBody = document.getElementById("operationsBody");
    activitiesBody.innerHTML = operations.scheduled_activities
      .map((item) => {
        const when = item.activity_date || dayNames[item.weekday] || "—";
        return `<tr><td><strong>${esc(item.label)}</strong><br><span class="pill">${esc(item.category)}</span></td><td>${esc(when)}</td><td>${item.start_time}–${item.end_time}</td><td>${item.assigned_teacher_ids.length}/${item.required_staff}</td><td>${esc(item.assigned_teacher_ids.map(teacherName).join(", ") || "Sin asignar")}</td><td><button class="btn small danger" data-remove-activity="${esc(item.id)}">Eliminar</button></td></tr>`;
      })
      .join("");
  }

  async function loadOperations() {
    const current = workspace();
    if (!current) return;
    try {
      const data = await request(`/schools/${current.schoolId}/operations`, {headers: headers(true)});
      operations = {
        recess_shifts: data.recess_shifts || [],
        scheduled_activities: data.scheduled_activities || [],
      };
      renderOperations();
    } catch (error) {
      document.getElementById("operationsStatus").textContent = `No se pudo cargar: ${error.message}`;
    }
  }

  async function saveOperations() {
    const current = workspace();
    if (!current) return;
    try {
      await request(`/schools/${current.schoolId}/operations`, {
        method: "PUT",
        headers: headers(true),
        body: JSON.stringify(operations),
      });
      status("operationsStatus", "Recreos y actividades guardados.", "ok");
    } catch (error) {
      status("operationsStatus", `No se pudo guardar: ${error.message}`, "error");
    }
  }

  document.getElementById("saveRecessBtn").onclick = () => {
    const id = idify(document.getElementById("recessId").value);
    if (!id) return alert("Indica un ID para el turno.");
    const item = {
      id,
      label: document.getElementById("recessLabel").value.trim() || id,
      weekday: Number(document.getElementById("recessDay").value),
      start_time: document.getElementById("recessStart").value,
      end_time: document.getElementById("recessEnd").value,
      location: document.getElementById("recessLocation").value.trim() || null,
      required_staff: Number(document.getElementById("recessStaff").value || 1),
      assigned_teacher_ids: selectedTeachers("recessTeachers"),
      active: true,
      notes: document.getElementById("recessNotes").value.trim() || null,
    };
    operations.recess_shifts = operations.recess_shifts.filter((row) => row.id !== id).concat(item);
    renderOperations();
  };

  document.getElementById("operationScheduleType").onchange = (event) => {
    const concreteDate = event.target.value === "date";
    document.getElementById("operationDayWrap").classList.toggle("hidden", concreteDate);
    document.getElementById("operationDateWrap").classList.toggle("hidden", !concreteDate);
  };

  document.getElementById("saveActivityBtn").onclick = () => {
    const id = idify(document.getElementById("operationId").value);
    if (!id) return alert("Indica un ID para la actividad.");
    const concreteDate = document.getElementById("operationScheduleType").value === "date";
    const item = {
      id,
      label: document.getElementById("operationLabel").value.trim() || id,
      category: document.getElementById("operationCategory").value,
      weekday: concreteDate ? null : Number(document.getElementById("operationDay").value),
      activity_date: concreteDate ? document.getElementById("operationDate").value || null : null,
      start_time: document.getElementById("operationStart").value,
      end_time: document.getElementById("operationEnd").value,
      location: document.getElementById("operationLocation").value.trim() || null,
      required_staff: Number(document.getElementById("operationStaff").value || 1),
      assigned_teacher_ids: selectedTeachers("operationTeachers"),
      movable: document.getElementById("operationMovable").checked,
      cancelable: document.getElementById("operationCancelable").checked,
      notes: document.getElementById("operationNotes").value.trim() || null,
    };
    if (concreteDate && !item.activity_date) return alert("Selecciona una fecha.");
    operations.scheduled_activities = operations.scheduled_activities
      .filter((row) => row.id !== id)
      .concat(item);
    renderOperations();
  };

  document.getElementById("saveOperationsBtn").onclick = saveOperations;
  document.getElementById("saveOperationsBtn2").onclick = saveOperations;
  document.getElementById("recessBody").onclick = (event) => {
    const id = event.target.dataset.removeRecess;
    if (!id) return;
    operations.recess_shifts = operations.recess_shifts.filter((item) => item.id !== id);
    renderOperations();
  };
  document.getElementById("operationsBody").onclick = (event) => {
    const id = event.target.dataset.removeActivity;
    if (!id) return;
    operations.scheduled_activities = operations.scheduled_activities.filter((item) => item.id !== id);
    renderOperations();
  };

  nav.addEventListener("click", (event) => {
    if (event.target.dataset.page === "recess" || event.target.dataset.page === "activities") {
      loadOperations();
    }
  });

  window.loadOperationsPlanning = loadOperations;
})();
