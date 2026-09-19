import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.core.audit import client_ip, record_audit_event
from app.core.config import settings
from app.core.database import engine
from app.core.rate_limit import limiter
from app.models import AuditAction, AuditResult
from app.modules.appointments.router import router as appointments_router
from app.modules.auth.router import router as auth_router
from app.modules.clinics.router import router as clinics_router
from app.modules.patients.router import router as patients_router
from app.modules.staff.router import router as staff_router

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title=settings.APP_NAME,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

app.state.limiter = limiter


async def _rate_limit_exceeded_with_audit(request: Request, exc: Exception) -> Response:
    record_audit_event(
        action=AuditAction.RATE_LIMITED,
        result=AuditResult.DENIED,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"path": request.url.path},
    )
    # slowapi's bundled handler is typed for its own decorator-based usage,
    # not Starlette's generic (Request, Exception) -> Response signature —
    # a known, narrow mismatch between the two libraries' type stubs, not a
    # real bug (it's called correctly at runtime for RateLimitExceeded).
    return _rate_limit_exceeded_handler(request, exc)  # type: ignore[arg-type]


app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_with_audit)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,  # required for httpOnly cookie auth across origins
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """
    Baseline defense-in-depth headers. None of these replace the app-level
    controls already in place (CSRF tokens, httpOnly cookies) — they narrow
    what a browser will do if something else ever goes wrong (a stray XSS,
    a clickjacking attempt, a MIME-sniffing quirk).
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


@app.get("/health", tags=["system"])
def health() -> dict:
    """Liveness probe — process is up. Does not touch the database."""
    return {"status": "ok"}


@app.get("/ready", tags=["system"])
def ready() -> dict:
    """Readiness probe — verifies the database connection actually works."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception:
        return {"status": "not_ready", "database": "unreachable"}


app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(clinics_router, prefix="/api/v1/clinics", tags=["clinics"])
app.include_router(patients_router, prefix="/api/v1/patients", tags=["patients"])
app.include_router(staff_router, prefix="/api/v1/staff", tags=["staff"])
app.include_router(appointments_router, prefix="/api/v1/appointments", tags=["appointments"])
