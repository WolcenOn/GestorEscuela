(() => {
  const style = document.createElement("style");
  style.textContent = `
    .plan-slot { margin-top:18px; border:1px solid #d8dee9; border-radius:16px; overflow:hidden; background:#fff; box-shadow:0 1px 2px rgba(16,24,40,.04); }
    .plan-slot-header { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:13px 16px; background:#eef2f6; border-bottom:2px solid #cbd5e1; }
    .plan-slot-header strong { font-size:16px; color:#172033; }
    .plan-slot-header span { color:#667085; font-size:12px; font-weight:750; }
    .plan-slot-body { padding:14px 16px 16px; }
    .plan-substitution { padding:12px; border:1px solid #e2e8f0; border-radius:12px; margin-bottom:12px; background:#fafbfc; }
    .plan-substitution.warning { background:#fff7ed; border-color:#fdba74; }
    .plan-substitution-title { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
    .plan-substitution-title strong { font-size:14px; }
    .candidate-table { margin-top:10px; }
    .candidate-table tr.selected-row { background:#ecfdf3; }
    .candidate-table tr.warning-row { background:#fff7ed; }
    .stats { display:flex; flex-wrap:wrap; gap:5px; margin-top:5px; }
    .stat-chip { display:inline-flex; gap:4px; align-items:center; padding:3px 7px; border-radius:999px; background:#f2f4f7; color:#475467; font-size:10px; font-weight:750; white-space:nowrap; }
    .stat-chip strong { font-size:10px; color:#172033; }
    .reason-text { display:block; margin-top:5px; color:#667085; font-size:11px; line-height:1.4; }
    .slot-summary { display:flex; flex-wrap:wrap; gap:6px; }
    .slot-summary .pill { background:#fff; border:1px solid #d0d5dd; }
  `;
  document.head.appendChild(style);

  let latestSolution = null;
  let latestStats = {};
  let statsRequestKey = "";

  function isWarning(item) {
    return item?.status === "WARNING_ALTERNATIVE" ||
      /cobertura excepcional|falta de especialidad|sin especialidad/i.test(item?.detail || "") ||
      /sin especialidad/i.test(item?.warning || "");
  }

  function slotInfo(slotId) {
    const slot = config.time_slots.find(item => item.id === slotId);
    return { id: slotId, label: slot?.label || slotId, order: slot?.order ?? 999 };
  }

  function statsFor(teacherId) {
    return latestStats[teacherId] || {
      historical_total: config.teachers.find(item => item.id === teacherId)?.substitution_count || 0,
      last_30_days: 0,
      last_7_days: 0,
    };
  }

  function statsHtml(teacherId) {
    const stats = statsFor(teacherId);
    return `<div class="stats">
      <span class="stat-chip">Histórico <strong>${stats.historical_total ?? 0}</strong></span>
      <span class="stat-chip">30 días <strong>${stats.last_30_days ?? 0}</strong></span>
      <span class="stat-chip">7 días <strong>${stats.last_7_days ?? 0}</strong></span>
    </div>`;
  }

  function candidateRows(assessments, activityId) {
    const items = assessments
      .filter(item => item.activity_id === activityId)
      .sort((a, b) => {
        if (a.status === "SELECTED") return -1;
        if (b.status === "SELECTED") return 1;
        if (a.status === "REJECTED" && b.status !== "REJECTED") return 1;
        if (b.status === "REJECTED" && a.status !== "REJECTED") return -1;
        return (a.penalty ?? 999999) - (b.penalty ?? 999999);
      });

    return items.map(item => {
      const warning = isWarning(item);
      const selected = item.status === "SELECTED";
      const rejected = item.status === "REJECTED";
      const state = selected ? "Elegido" : rejected ? "Descartado" : warning ? "Alternativa excepcional" : "Alternativa válida";
      const rowClass = selected ? "selected-row" : warning ? "warning-row" : "";
      const reason = item.warning || item.detail || item.rejection_reason || "Sin observaciones.";
      return `<tr class="${rowClass}">
        <td><strong>${esc(teacherName(item.teacher_id))}</strong>${statsHtml(item.teacher_id)}</td>
        <td>${item.penalty ?? "—"}</td>
        <td>${warning ? `<span class="warning-pill">⚠ Sin especialidad</span><br>` : ""}<strong>${esc(state)}</strong><span class="reason-text">${esc(reason)}</span></td>
      </tr>`;
    }).join("");
  }

  function renderPlan(sol) {
    const subs = sol.substitutions || [];
    const unc = sol.uncovered || [];
    const assessments = sol.candidate_assessments || [];
    const coverage = Math.round((sol.coverage_ratio || 0) * 100);
    const relevantSlotIds = [...new Set([
      ...subs.map(item => item.slot_id),
      ...unc.map(item => item.slot_id),
      ...assessments.map(item => item.slot_id),
    ])];
    const slots = relevantSlotIds.map(slotInfo).sort((a, b) => a.order - b.order);

    const slotBlocks = slots.map(slot => {
      const slotSubs = subs.filter(item => item.slot_id === slot.id);
      const slotUncovered = unc.filter(item => item.slot_id === slot.id);
      const activityIds = [...new Set([
        ...slotSubs.map(item => item.activity_id),
        ...assessments.filter(item => item.slot_id === slot.id).map(item => item.activity_id),
      ])];

      const needs = activityIds.map(activityId => {
        const substitution = slotSubs.find(item => item.activity_id === activityId);
        const selectedAssessment = substitution ? assessments.find(item =>
          item.activity_id === activityId &&
          item.teacher_id === substitution.substitute_teacher_id &&
          item.status === "SELECTED"
        ) : null;
        const warning = isWarning(selectedAssessment);
        const groupId = substitution?.group_id || assessments.find(item => item.activity_id === activityId)?.group_id || "—";
        const absentId = substitution?.absent_teacher_id || "—";
        const proposal = substitution
          ? `<div class="plan-substitution ${warning ? "warning" : ""}">
              <div class="plan-substitution-title">
                <div><strong>${esc(groupId)} · ${esc(teacherName(absentId))} → ${esc(teacherName(substitution.substitute_teacher_id))}</strong>
                  <span class="reason-text">Propuesta seleccionada · coste ${substitution.penalty ?? "—"}</span>
                  ${statsHtml(substitution.substitute_teacher_id)}
                </div>
                ${warning ? `<span class="warning-pill">⚠ Sin especialidad requerida</span>` : `<span class="pill">Cobertura propuesta</span>`}
              </div>
            </div>`
          : "";
        const rows = candidateRows(assessments, activityId);
        return `${proposal}${rows ? `<table class="candidate-table"><thead><tr><th>Docente y carga</th><th>Coste</th><th>Razón / valoración</th></tr></thead><tbody>${rows}</tbody></table>` : ""}`;
      }).join("");

      const uncoveredHtml = slotUncovered.length
        ? `<div class="status error">${slotUncovered.map(item => `${esc(item.group_id)}: ${esc(item.reason)}`).join("<br>")}</div>`
        : "";

      return `<section class="plan-slot" data-slot-id="${esc(slot.id)}">
        <div class="plan-slot-header">
          <div><strong>${esc(slot.label)}</strong><br><span>${esc(slot.id)}</span></div>
          <div class="slot-summary"><span class="pill">${slotSubs.length} sustitución${slotSubs.length === 1 ? "" : "es"}</span>${slotUncovered.length ? `<span class="pill">${slotUncovered.length} sin cubrir</span>` : ""}</div>
        </div>
        <div class="plan-slot-body">${needs || `<span class="muted">Sin decisiones en esta franja.</span>`}${uncoveredHtml}</div>
      </section>`;
    }).join("");

    document.getElementById("results").innerHTML = `
      <div class="cards">
        <div class="card metric"><span>Cobertura</span><strong>${coverage}%</strong></div>
        <div class="card metric"><span>Puntuación</span><strong>${sol.score ?? "—"}</strong></div>
        <div class="card metric"><span>Sustituciones</span><strong>${subs.length}</strong></div>
        <div class="card metric"><span>Sin cubrir</span><strong>${unc.length}</strong></div>
      </div>
      <div class="card" style="margin-top:14px">
        <div class="section-title"><h3>Plan por franjas</h3><span class="muted">Cada hora agrupa su propuesta, estadísticas y razones de los candidatos.</span></div>
        ${slotBlocks || `<p class="muted">No hay decisiones de sustitución para este plan.</p>`}
      </div>
    `;
  }

  async function loadStatsForCurrentPlan() {
    const w = workspace();
    const planDate = document.getElementById("planDate")?.value;
    if (!w || !planDate) return;
    const key = `${w.schoolId}:${planDate}`;
    statsRequestKey = key;
    try {
      const data = await request(`/schools/${w.schoolId}/substitution-statistics?plan_date=${encodeURIComponent(planDate)}`, { headers: headers(true) });
      if (statsRequestKey !== key) return;
      latestStats = Object.fromEntries((data.teachers || []).map(item => [item.teacher_id, item]));
      if (latestSolution) renderPlan(latestSolution);
    } catch (_) {
      // The plan remains usable even if statistics cannot be refreshed.
    }
  }

  renderResults = function phase10RenderResults(sol) {
    latestSolution = sol;
    latestStats = {};
    renderPlan(sol);
    void loadStatsForCurrentPlan();
  };
})();
