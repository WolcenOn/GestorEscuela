from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page, expect


pytestmark = pytest.mark.e2e


def base_url() -> str:
    return os.getenv("PLAYWRIGHT_BASE_URL", "http://127.0.0.1:8000")


def test_operator_can_configure_school_and_solve_absence(page: Page) -> None:
    page.goto(base_url())

    expect(page).to_have_title("GestorEscuela")
    expect(page.get_by_role("heading", name="Configura tu espacio de trabajo")).to_be_visible()

    page.get_by_label("Tu nombre").fill("Playwright Admin")
    page.get_by_label("Email").fill("playwright@example.test")
    page.get_by_label("Nombre del centro").fill("CEIP Playwright")
    page.get_by_role("button", name="Usar datos de ejemplo").click()
    page.get_by_role("button", name="Crear centro").click()

    expect(page.get_by_role("heading", name="Operativa del día")).to_be_visible()
    expect(page.locator("#mTeachers")).not_to_have_text("0")
    expect(page.locator("#mGroups")).not_to_have_text("0")
    expect(page.locator("#mSubjects")).not_to_have_text("0")
    expect(page.locator("#mLessons")).not_to_have_text("0")

    page.get_by_role("button", name="Horario").click()
    expect(page.get_by_role("heading", name="Horario semanal")).to_be_visible()
    expect(page.locator("#scheduleBody .lesson").first).to_be_visible()

    page.get_by_role("button", name="Hoy").click()
    page.get_by_role("button", name="+ Añadir ausencia").click()

    absence = page.locator("#absenceList .absence").first
    expect(absence.locator("select")).to_be_visible()
    absence.locator('input[type="checkbox"]').first.check()

    page.get_by_role("button", name="Calcular sustituciones").click()

    expect(page.locator("#solveStatus")).to_contain_text("Plan resuelto")
    expect(page.locator("#results")).to_contain_text("Cobertura")
    expect(page.locator("#results")).to_contain_text("Propuesta")
