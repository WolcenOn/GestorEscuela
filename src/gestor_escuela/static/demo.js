(() => {
  const setup = document.getElementById("setup");
  if (!setup) return;

  const oldDemoButton = document.getElementById("demoBtn");
  if (oldDemoButton) oldDemoButton.classList.add("hidden");

  const setupActions = setup.querySelector(".actions");
  const button = document.createElement("button");
  button.id = "completeDemoBtn";
  button.className = "btn primary";
  button.textContent = "Probar centro demo completo";
  setupActions?.prepend(button);

  const headerActions = document.querySelector("header .actions");
  const restoreButton = document.createElement("button");
  restoreButton.id = "restoreDemoBtn";
  restoreButton.className = "btn";
  restoreButton.textContent = "Cargar demo completo";
  headerActions?.prepend(restoreButton);

  const hint = document.createElement("p");
  hint.className = "muted";
  hint.textContent =
    "Crea automáticamente un centro de ejemplo con horario semanal completo y una ausencia preparada para probar el motor.";
  setupActions?.insertAdjacentElement("afterend", hint);

  const groupDefs = [
    ["1A", "1º A", "Primaria · 1º", "P01"],
    ["1B", "1º B", "Primaria · 1º", "P02"],
    ["2A", "2º A", "Primaria · 2º", "P03"],
    ["2B", "2º B", "Primaria · 2º", "P04"],
    ["3A", "3º A", "Primaria · 3º", "P05"],
    ["4A", "4º A", "Primaria · 4º", "P06"],
  ];

  const teacherDefs = [
    ["P01", "Ana García", "TUTOR", []],
    ["P02", "Luis Martín", "TUTOR", []],
    ["P03", "Carmen Ruiz", "TUTOR", []],
    ["P04", "Javier Moreno", "TUTOR", []],
    ["P05", "Elena Sánchez", "TUTOR", []],
    ["P06", "Miguel Torres", "TUTOR", []],
    ["P07", "Laura Pérez", "SPECIALIST", ["ENGLISH"]],
    ["P08", "Carlos Vega", "SPECIALIST", ["PE"]],
    ["P09", "María León", "SPECIALIST", ["MUSIC"]],
    ["P10", "Rocío Díaz", "PT", ["PT"]],
    ["P11", "Andrés Gil", "AL", ["AL"]],
    ["P12", "Sonia Romero", "SUPPORT", []],
    ["P13", "Dirección", "MANAGEMENT", []],
  ];

  const subjects = [
    {id: "MAT", label: "Matemáticas", required_specialty: null},
    {id: "LEN", label: "Lengua", required_specialty: null},
    {id: "SCI", label: "Conocimiento del medio", required_specialty: null},
    {id: "ENG", label: "Inglés", required_specialty: "ENGLISH"},
    {id: "PE", label: "Educación Física", required_specialty: "PE"},
    {id: "MUS", label: "Música", required_specialty: "MUSIC"},
    {id: "ART", label: "Plástica", required_specialty: null},
  ];

  const timeSlots = [
    {id: "S1", label: "09:00–10:00", order: 1},
    {id: "S2", label: "10:00–11:00", order: 2},
    {id: "S3", label: "11:30–12:30", order: 3},
    {id: "S4", label: "12:30–13:15", order: 4},
    {id: "S5", label: "13:15–14:00", order: 5},
    {id: "S6", label: "14:00–15:00", order: 6},
  ];

  function schoolDayISO() {
    const date = new Date();
    const day = date.getDay();
    if (day === 6) date.setDate(date.getDate() + 2);
    if (day === 0) date.setDate(date.getDate() + 1);
    return date.toISOString().slice(0, 10);
  }

  function buildDemoConfig() {
    const groups = groupDefs.map(([id, label, stage, tutor_teacher_id]) => ({
      id,
      label,
      stage,
      tutor_teacher_id,
    }));
    const groupIds = groups.map((group) => group.id);
    const teachers = teacherDefs.map(([id, display_name, profile, specialties], index) => ({
      id,
      display_name,
      profile,
      substitution_count: index % 4,
      can_cover_groups: [...groupIds],
      specialties,
      emergency_only: false,
    }));

    const activities = [];
    const baseSubjects = ["MAT", "LEN", "SCI", "MAT", "LEN", "ART"];
    for (let weekday = 0; weekday < 5; weekday += 1) {
      groups.forEach((group, groupIndex) => {
        timeSlots.forEach((slot, slotIndex) => {
          let teacherId = group.tutor_teacher_id;
          let subjectId = baseSubjects[(slotIndex + weekday + groupIndex) % baseSubjects.length];
          let requiredSpecialty = null;

          if ((weekday === 0 || weekday === 2) && slotIndex === groupIndex) {
            teacherId = "P07";
            subjectId = "ENG";
            requiredSpecialty = "ENGLISH";
          } else if ((weekday === 1 || weekday === 3) && slotIndex === groupIndex) {
            teacherId = "P08";
            subjectId = "PE";
            requiredSpecialty = "PE";
          } else if (weekday === 4 && slotIndex === groupIndex) {
            teacherId = "P09";
            subjectId = "MUS";
            requiredSpecialty = "MUSIC";
          }

          activities.push({
            id: `A-${group.id}-${weekday}-${slot.id}`,
            weekday,
            slot_id: slot.id,
            activity_type: "CLASS",
            teacher_id: teacherId,
            group_id: group.id,
            subject_id: subjectId,
            required_specialty: requiredSpecialty,
            priority: 30,
            movable: false,
            cancelable: false,
          });
        });
      });
    }

    const supportActivities = [
      ["PT-1A", 0, "S3", "PT", "P10", "1A", 40],
      ["PT-3A", 2, "S4", "PT", "P10", "3A", 40],
      ["AL-1B", 1, "S3", "AL", "P11", "1B", 40],
      ["AL-2B", 3, "S4", "AL", "P11", "2B", 40],
      ["SUP-1", 0, "S2", "SUPPORT", "P12", null, 10],
      ["SUP-2", 1, "S5", "SUPPORT", "P12", null, 10],
      ["SUP-3", 2, "S2", "SUPPORT", "P12", null, 10],
      ["SUP-4", 3, "S5", "SUPPORT", "P12", null, 10],
      ["COORD", 4, "S6", "COORDINATION", "P13", null, 10],
    ];
    supportActivities.forEach(
      ([id, weekday, slot_id, activity_type, teacher_id, group_id, priority]) => {
        activities.push({
          id,
          weekday,
          slot_id,
          activity_type,
          teacher_id,
          group_id,
          subject_id: null,
          required_specialty:
            activity_type === "PT" ? "PT" : activity_type === "AL" ? "AL" : null,
          priority,
          movable: activity_type === "SUPPORT" || activity_type === "COORDINATION",
          cancelable: activity_type === "SUPPORT" || activity_type === "COORDINATION",
        });
      },
    );

    return {groups, subjects, time_slots: timeSlots, teachers, activities};
  }

  function prepareDemoView() {
    absences = [{teacher_id: "P01", slot_ids: ["S2"]}];
    document.getElementById("planDate").value = schoolDayISO();
    showApp();
    renderAll();
    navTo("schedule");
    document.getElementById("scheduleGroup").value = "1A";
    renderSchedule();
    document.getElementById("headerMeta").textContent =
      "Demo completa cargada · 6 grupos con 30 clases semanales cada uno";
  }

  async function saveDemoConfiguration(schoolId, actorId) {
    config = buildDemoConfig();
    await request(`/schools/${schoolId}/academic-configuration`, {
      method: "PUT",
      headers: {"Content-Type": "application/json", "X-Actor-Id": actorId},
      body: JSON.stringify(config),
    });
    prepareDemoView();
  }

  async function restoreDemoWorkspace() {
    const current = workspace();
    if (!current) {
      await createDemoWorkspace();
      return;
    }
    try {
      restoreButton.disabled = true;
      document.getElementById("headerMeta").textContent = "Cargando demo completa...";
      await saveDemoConfiguration(current.schoolId, current.actorId);
    } catch (error) {
      alert(`No se pudo cargar la demo: ${error.message}`);
    } finally {
      restoreButton.disabled = false;
    }
  }

  async function createDemoWorkspace() {
    try {
      button.disabled = true;
      status("setupStatus", "Creando centro demo y horario completo...");
      const token = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const user = await request("/users", {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-Actor-Role": "ADMIN"},
        body: JSON.stringify({
          email: `demo-${token}@gestorescuela.test`,
          display_name: "Dirección Demo",
        }),
      });
      const school = await request("/schools", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Actor-Id": user.id,
          "X-Actor-Role": "ADMIN",
        },
        body: JSON.stringify({name: "CEIP Horizonte · Demo"}),
      });
      await request(`/schools/${school.id}/memberships`, {
        method: "PUT",
        headers: {"Content-Type": "application/json", "X-Actor-Role": "ADMIN"},
        body: JSON.stringify({user_id: user.id, role: "ADMIN"}),
      });

      localStorage.setItem(
        stateKey,
        JSON.stringify({actorId: user.id, schoolId: school.id, schoolName: school.name}),
      );
      await saveDemoConfiguration(school.id, user.id);
    } catch (error) {
      status("setupStatus", error.message, "error");
      button.disabled = false;
    }
  }

  button.addEventListener("click", createDemoWorkspace);
  restoreButton.addEventListener("click", restoreDemoWorkspace);
})();
