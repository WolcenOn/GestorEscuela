from __future__ import annotations

import os
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from gestor_escuela.api.academic import router as academic_router
from gestor_escuela.api.academic_context import router as academic_context_router
from gestor_escuela.api.app import app
from gestor_escuela.api.audit import audit_mutating_requests
from gestor_escuela.api.auth_context import router as auth_context_router
from gestor_escuela.api.operations import router as operations_router
from gestor_escuela.api.plan_insights import router as plan_insights_router
from gestor_escuela.api.roster import router as roster_router
from gestor_escuela.api.security import MaxRequestBodyMiddleware, SecurityHeadersMiddleware
from gestor_escuela.api.staffing import router as staffing_router

_STATIC_DIR = Path(__file__).with_name("static")
_UI_FILE = _STATIC_DIR / "index.html"
_DEMO_FILE = _STATIC_DIR / "demo.js"
_OPERATIONS_FILE = _STATIC_DIR / "operations.js"
_PHASE9_FILE = _STATIC_DIR / "phase9.js"
_PHASE10_FILE = _STATIC_DIR / "phase10.js"


def _cors_origins() -> list[str]:
    """Origins allowed to call the deployed API from a separate browser frontend.

    The production default only enables the GitHub Pages origin used by Horario PT / AL.
    Additional local or preview origins can be supplied as a comma-separated CORS_ORIGINS
    environment variable without changing application code.
    """

    configured = os.getenv("CORS_ORIGINS", "https://wolcenon.github.io")
    return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]


app.middleware("http")(audit_mutating_requests)
app.add_middleware(MaxRequestBodyMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

origins = _cors_origins()
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Actor-Id", "X-Actor-Role", "Authorization"],
        expose_headers=["X-Request-Id"],
    )

app.include_router(academic_router)
app.include_router(academic_context_router)
app.include_router(auth_context_router)
app.include_router(operations_router)
app.include_router(plan_insights_router)
app.include_router(roster_router)
app.include_router(staffing_router)


@app.get("/", include_in_schema=False)
def operator_ui() -> HTMLResponse:
    html = _UI_FILE.read_text(encoding="utf-8")
    scripts = (
        '<script src="/demo.js"></script>'
        '<script src="/operations.js"></script>'
        '<script src="/phase9.js"></script>'
        '<script src="/phase10.js"></script>'
    )
    html = html.replace("</body>", f"{scripts}</body>")
    return HTMLResponse(html)


@app.get("/demo.js", include_in_schema=False)
def demo_script() -> FileResponse:
    return FileResponse(_DEMO_FILE, media_type="application/javascript")


@app.get("/operations.js", include_in_schema=False)
def operations_script() -> FileResponse:
    return FileResponse(_OPERATIONS_FILE, media_type="application/javascript")


@app.get("/phase9.js", include_in_schema=False)
def phase9_script() -> FileResponse:
    return FileResponse(_PHASE9_FILE, media_type="application/javascript")


@app.get("/phase10.js", include_in_schema=False)
def phase10_script() -> FileResponse:
    return FileResponse(_PHASE10_FILE, media_type="application/javascript")
