from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def base_url() -> str:
    return os.getenv("PLAYWRIGHT_BASE_URL", "http://127.0.0.1:8000")


def test_complete_demo_can_solve_prepared_absence(page: Page) -> None:
    page.goto(base_url())

    expect(page).to_have_title("GestorEscuela")
    expect(page.get_by_role("heading", name="Configura tu espacio de trabajo")).to_be_visible()

    page.get_by_role("button", name="Probar centro demo completo").click()

    expect(page.get_by_role("heading", name="Horario semanal")).to_be_visible()
    expect(page.locator("#mTeachers")).to_have_text("13")
    expect(page.locator("#mGroups")).to_have_text("6")
    expect(page.locator("#mSubjects")).to_have_text("7")
    expect(page.locator("#mLessons")).to_have_text("180")

    group_select = page.locator("#scheduleGroup")
    for group_id in ("1A", "1B", "2A", "2B", "3A", "4A"):
        group_select.select_option(group_id)
        timetable_cells = page.locator("#scheduleBody .slot-cell")
        expect(timetable_cells).to_have_count(30)
        for cell_index in range(30):
            expect(timetable_cells.nth(cell_index).locator(".lesson").first).to_be_visible()

    expect(page.get_by_role("button", name="Cargar demo completo")).to_be_visible()

    page.get_by_role("button", name="Hoy").click()
    absence = page.locator("#absenceList .absence").first
    expect(absence).to_be_visible()
    expect(absence.locator('input[type="checkbox"]:checked')).to_have_count(1)

    page.get_by_role("button", name="Calcular sustituciones").click()

    expect(page.locator("#solveStatus")).to_contain_text("Plan resuelto")
    expect(page.locator("#results")).to_contain_text("Cobertura")
    expect(page.locator("#results")).to_contain_text("Propuesta")
