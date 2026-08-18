from fastapi.testclient import TestClient

from gestor_escuela.web import app


def test_demo_script_exposes_reload_button() -> None:
    response = TestClient(app).get("/demo.js")
    assert response.status_code == 200
    assert "Cargar demo completo" in response.text
    assert "30 clases semanales cada uno" in response.text
