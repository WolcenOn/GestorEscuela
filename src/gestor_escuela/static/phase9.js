(() => {
  const orangeStyle = document.createElement("style");
  orangeStyle.textContent = `
    .candidate-warning { background:#fff7ed; color:#9a3412; }
    .candidate-warning td { border-bottom-color:#fed7aa; }
    .warning-pill { display:inline-flex;align-items:center;border-radius:999px;padding:4px 8px;background:#ffedd5;color:#9a3412;font-size:11px;font-weight:800; }
    .teacher-free { background:#f8fafc; color:#667085; border-left:3px solid #cbd5e1; }
    .teacher-coordination { background:#f5f3ff; border-left-color:#7c3aed; }
    .teacher-support { background:#ecfdf3; border-left-color:#059669; }
  `;
  document.head.appendChild(orangeStyle);

  function activityLabel(activity) {
    if (!activity) return "Libre";
    const type = activity.activity_type || "ACTIVITY";
    const group = config.groups.find(groupItem => groupItem.id === activity.group_id);
    const subject = config.subjects.find(subjectItem => subjectItem.id === activity.subject_id);
    if (type === "CLASS") return `${subject?.label || "Clase"}${group ? ` · ${group.label}` : ""}`;
    if (type === "COORDINATION") return "Coordinación";
    if (type === "SUPPORT") return `Apoyo${group ? ` · ${group.label}` : ""}`;
    if (type === "PT" || type === "AL") return `${type}${group ? ` · ${group.label}` : ""}`;
    return `${type}${group ? ` · ${group.label}` : ""}`;
  }

  function teacherActivityClass(activity) {
    if (!activity) return "lesson teacher-free";
    if (activity.activity_type === "COORDINATION") return "lesson teacher-coordination";
    if (["SUPPORT", "PT", "AL"].includes(activity.activity_type)) return "lesson teacher-support";
    return "lesson";
  }

  function ensureTeacherScheduleControls() {
    const schedulePage = document.getElementById("page-schedule");
    if (!schedulePage) return;
    const toolbar = schedulePage.querySelector(".toolbar");
    if (!toolbar || document.getElementById("scheduleMode")) return;

    const groupLabel = document.getElementById("scheduleGroup")?.closest("label");
    if (groupLabel) groupLabel.id = "scheduleGroupLabel";

    const modeLabel = document.createElement("label");
    modeLabel.innerHTML = `Ver horario por<select id="scheduleMode"><option value="group">Grupo</option><option value="teacher">Docente</option></select>`;
    toolbar.prepend(modeLabel);

    const teacherLabel = document.createElement("label");
    teacherLabel.id = "scheduleTeacherLabel";
    teacherLabel.style.display = "none";
    teacherLabel.innerHTML = `Docente<select id="scheduleTeacher"></select>`;
    toolbar.appendChild(teacherLabel);

    document.getElementById("scheduleMode").addEventListener("change", () => {
      const teacherMode = document.getElementById("scheduleMode").value === "teacher";
      document.getElementById("scheduleGroupLabel").style.display = teacherMode ? "none" : "grid";
      teacherLabel.style.display = teacherMode ? "grid" : "none";
      renderSchedule();
    });
    document.getElementById("scheduleTeacher").addEventListener("change", renderSchedule);
  }

  function refreshTeacherOptions() {
    const select = document.getElementById("scheduleTeacher");
    if (!select) return;
    const previous = select.value;
    select.innerHTML = config.teachers
      .map(teacher => `<option value="${esc(teacher.id)}">${esc(teacher.display_name || teacher.id)}</option>`)
      .join("");
    if (config.teachers.some(teacher => teacher.id === previous)) select.value = previous;
  }

  const baseRenderAll = renderAll;
  renderAll = function phase9RenderAll() {
    baseRenderAll();
    ensureTeacherScheduleControls();
    refreshTeacherOptions();
  };

  const baseRenderSchedule = renderSchedule;
  renderSchedule = function phase9RenderSchedule() {
    ensureTeacherScheduleControls();
    refreshTeacherOptions();
    const mode = document.getElementById("scheduleMode")?.value || "group";
    if (mode !== "teacher") {
      baseRenderSchedule();
      return;
    }

    const teacherId = document.getElementById("scheduleTeacher")?.value || config.teachers[0]?.id;
    const body = document.getElementById("scheduleBody");
    if (!body || !teacherId) {
      if (body) body.innerHTML = "";
      return;
    }

    const slots = [...config.time_slots].sort((a, b) => a.order - b.order);
    body.innerHTML = slots.map(slot => {
      const cells = [0, 1, 2, 3, 4].map(day => {
        const activities = config.activities.filter(activity =>
          activity.teacher_id === teacherId &&
          activity.slot_id === slot.id &&
          (activity.weekday === day || activity.weekday == null)
        );
        if (!activities.length) {
          return `<td><div class="${teacherActivityClass(null)}"><strong>LIBRE</strong><span>Disponible en esta franja</span></div></td>`;
        }
        return `<td>${activities.map(activity => `<div class="${teacherActivityClass(activity)}"><strong>${esc(activityLabel(activity))}</strong><span>${esc(activity.activity_type)}</span></div>`).join("")}</td>`;
      }).join("");
      return `<tr><th>${esc(slot.label)}</th>${cells}</tr>`;
    }).join("");
  };

  function isSpecialtyWarning(assessment) {
    return assessment.status === "WARNING_ALTERNATIVE" ||
      /cobertura excepcional|falta de especialidad|sin especialidad/i.test(assessment.detail || "");
  }

  renderResults = function phase9RenderResults(sol) {
    const subs = sol.substitutions || [];
    const unc = sol.uncovered || [];
    const assessments = sol.candidate_assessments || [];
    const rejected = assessments.filter(item => item.status === "REJECTED");
    const ranked = assessments
      .filter(item => item.status !== "REJECTED")
      .sort((a, b) => (a.penalty ?? 999999) - (b.penalty ?? 999999));
    const coverage = Math.round((sol.coverage_ratio || 0) * 100);

    const proposalRows = subs.map(substitution => {
      const assessment = assessments.find(item =>
        item.activity_id === substitution.activity_id &&
        item.teacher_id === substitution.substitute_teacher_id &&
        item.status === "SELECTED"
      );
      const warning = assessment && isSpecialtyWarning(assessment);
      return `<tr class="${warning ? "candidate-warning" : ""}"><td>${esc(substitution.slot_id)}</td><td>${esc(substitution.group_id)}</td><td>${esc(teacherName(substitution.absent_teacher_id))}</td><td><strong>${esc(teacherName(substitution.substitute_teacher_id))}</strong>${warning ? `<br><span class="warning-pill">⚠ Sin especialidad requerida</span>` : ""}</td></tr>`;
    }).join("") || `<tr><td colspan="4">No se requieren sustituciones.</td></tr>`;

    const rankingRows = ranked.map(item => {
      const warning = isSpecialtyWarning(item);
      const state = item.status === "SELECTED" ? "Elegido" : warning ? "Alternativa excepcional" : "Alternativa válida";
      return `<tr class="${warning ? "candidate-warning" : ""}"><td><strong>${esc(teacherName(item.teacher_id))}</strong></td><td>${esc(item.group_id)} · ${esc(item.slot_id)}</td><td>${item.penalty ?? "—"}</td><td>${warning ? `<span class="warning-pill">⚠ Sin especialidad</span><br>` : ""}${esc(state)}${item.detail ? `<br><span class="muted">${esc(item.detail)}</span>` : ""}</td></tr>`;
    }).join("");

    document.getElementById("results").innerHTML = `
      <div class="cards">
        <div class="card metric"><span>Cobertura</span><strong>${coverage}%</strong></div>
        <div class="card metric"><span>Puntuación</span><strong>${sol.score ?? "—"}</strong></div>
        <div class="card metric"><span>Sustituciones</span><strong>${subs.length}</strong></div>
        <div class="card metric"><span>Sin cubrir</span><strong>${unc.length}</strong></div>
      </div>
      <div class="card" style="margin-top:14px">
        <div class="section-title"><h3>Propuesta</h3></div>
        <table><thead><tr><th>Franja</th><th>Grupo</th><th>Ausente</th><th>Sustituto</th></tr></thead><tbody>${proposalRows}</tbody></table>
        ${unc.length ? `<p class="status error">${unc.map(item => `${esc(item.group_id)} · ${esc(item.slot_id)}: ${esc(item.reason)}`).join("<br>")}</p>` : ""}
      </div>
      ${rankingRows ? `<div class="card" style="margin-top:14px"><div class="section-title"><h3>Ranking de candidatos</h3><span class="muted">Las alternativas naranjas son coberturas excepcionales sin la especialidad requerida.</span></div><table><thead><tr><th>Docente</th><th>Necesidad</th><th>Coste</th><th>Valoración</th></tr></thead><tbody>${rankingRows}</tbody></table></div>` : ""}
      ${rejected.length ? `<div class="card" style="margin-top:14px"><details><summary>Ver ${rejected.length} candidatos descartados</summary><table><tbody>${rejected.map(item => `<tr><td>${esc(teacherName(item.teacher_id))}</td><td>${esc(item.detail || item.rejection_reason)}</td></tr>`).join("")}</tbody></table></details></div>` : ""}
    `;
  };

  ensureTeacherScheduleControls();
  refreshTeacherOptions();
})();
