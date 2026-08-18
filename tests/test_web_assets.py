from fastapi.testclient import TestClient

from gestor_escuela.web import app

client = TestClient(app)


def test_demo_script_is_served() -> None:
    response = client.get("/demo.js")

    assert response.status_code == 200
    assert "Probar centro demo completo" in response.text
