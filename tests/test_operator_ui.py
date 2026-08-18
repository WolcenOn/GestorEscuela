from fastapi.testclient import TestClient

from gestor_escuela.web import app


def test_operator_ui_is_served_at_root() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "GestorEscuela" in response.text
    assert "Calcular sustituciones" in response.text
