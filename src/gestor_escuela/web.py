from __future__ import annotations

from pathlib import Path

from fastapi.responses import FileResponse

from gestor_escuela.api.academic import router as academic_router
from gestor_escuela.api.app import app

_UI_FILE = Path(__file__).with_name("static") / "index.html"

app.include_router(academic_router)


@app.get("/", include_in_schema=False)
def operator_ui() -> FileResponse:
    return FileResponse(_UI_FILE, media_type="text/html")
