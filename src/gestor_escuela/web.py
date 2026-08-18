from __future__ import annotations

from pathlib import Path

from fastapi.responses import FileResponse, HTMLResponse

from gestor_escuela.api.academic import router as academic_router
from gestor_escuela.api.app import app
from gestor_escuela.api.operations import router as operations_router

_STATIC_DIR = Path(__file__).with_name("static")
_UI_FILE = _STATIC_DIR / "index.html"
_DEMO_FILE = _STATIC_DIR / "demo.js"
_OPERATIONS_FILE = _STATIC_DIR / "operations.js"

app.include_router(academic_router)
app.include_router(operations_router)


@app.get("/", include_in_schema=False)
def operator_ui() -> HTMLResponse:
    html = _UI_FILE.read_text(encoding="utf-8")
    scripts = '<script src="/demo.js"></script><script src="/operations.js"></script>'
    html = html.replace("</body>", f"{scripts}</body>")
    return HTMLResponse(html)


@app.get("/demo.js", include_in_schema=False)
def demo_script() -> FileResponse:
    return FileResponse(_DEMO_FILE, media_type="application/javascript")


@app.get("/operations.js", include_in_schema=False)
def operations_script() -> FileResponse:
    return FileResponse(_OPERATIONS_FILE, media_type="application/javascript")
