import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.audit import client_ip, record_audit_event
from app.core.config import settings
from app.core.database import engine
from app.core.logging_setup import configure_logging
from app.core.metrics import (
    db_errors_total,
    http_request_duration_seconds_count,
    http_request_duration_seconds_sum,
    http_requests_total,
    rate_limit_events_total,
    render_prometheus_text,
    status_class,
)
from app.core.rate_limit import limiter
from app.core.request_context import (
    REQUEST_ID_HEADER,
    bind_request_id,
    get_request_id,
    new_request_id,
    reset_request_id,
)
from app.models import AuditAction, AuditResult
from app.modules.appointments.router import router as appointments_router
from app.modules.auth.router import router as auth_router
from app.modules.clinics.router import router as clinics_router
from app.modules.consents.router import router as consents_router
from app.modules.medical_records.router import router as medical_records_router
from app.modules.medications.router import router as medications_router
from app.modules.notifications.router import router as notifications_router
from app.modules.patients.router import router as patients_router
from app.modules.staff.router import router as staff_router

# JSON in anything that isn't plain local development — staging logs get
# shipped/ingested the same way production's do, so they need the same
# machine-readable shape.
configure_logging(debug=settings.DEBUG, json_output=settings.ENVIRONMENT != "development")
logger = logging.getLogger("myvita.request")

app = FastAPI(
    title=settings.APP_NAME,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

app.state.limiter = limiter


async def _rate_limit_exceeded_with_audit(request: Request, exc: Exception) -> Response:
    rate_limit_events_total.inc()
    record_audit_event(
        action=AuditAction.RATE_LIMITED,
        result=AuditResult.DENIED,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"path": request.url.path, "request_id": get_request_id()},
    )
    # slowapi's bundled handler is typed for its own decorator-based usage,
    # not Starlette's generic (Request, Exception) -> Response signature —
    # a known, narrow mismatch between the two libraries' type stubs, not a
    # real bug (it's called correctly at runtime for RateLimitExceeded).
    return _rate_limit_exceeded_handler(request, exc)  # type: ignore[arg-type]


async def _database_error_handler(request: Request, exc: Exception) -> Response:
    db_errors_total.inc()
    # Safe fields only: exception TYPE, not str(exc) — SQLAlchemy exception
    # messages routinely include the failed statement and its bound
    # parameters, which can be clinical data or credentials. request_id
    # lets an operator correlate this with the DB server's own logs.
    logger.error(
        "database_error path=%s method=%s exception_type=%s",
        request.url.path,
        request.method,
        type(exc).__name__,
    )
    return JSONResponse(status_code=503, content={"detail": "Serviço temporariamente indisponível."})


async def _unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    # Anything reaching here is a bug, not an expected error path (those
    # raise HTTPException, which FastAPI already handles separately and
    # never reaches this handler). The client gets nothing but a generic
    # message — no stack trace, no exception message, no internals.
    log = logger.exception if settings.DEBUG else logger.error
    log(
        "unhandled_exception path=%s method=%s exception_type=%s",
        request.url.path,
        request.method,
        type(exc).__name__,
    )
    return JSONResponse(status_code=500, content={"detail": "Erro interno do servidor."})


app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_with_audit)
app.add_exception_handler(SQLAlchemyError, _database_error_handler)
app.add_exception_handler(Exception, _unhandled_exception_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,  # required for httpOnly cookie auth across origins
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


def _apply_security_headers(request: Request, response: Response) -> None:
    """Apply browser and cache controls to every response, including 413s."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"


@app.middleware("http")
async def observability(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """
    Registered AFTER security_headers, which makes this the OUTERMOST
    middleware: its "before" code runs first (so request_id exists for
    everything downstream, including the exception handlers above) and its
    "after" code runs last (so it logs the final status code, headers and
    all).

    Logs exactly: method, path, status_code, duration_ms, request_id. Never
    query params, never the request body, never headers (that would include
    Cookie and Authorization) — see app/core/logging_setup.py for the
    formatter that turns this into JSON in production.
    """
    request_id = new_request_id(request.headers.get(REQUEST_ID_HEADER))
    token = bind_request_id(request_id)
    request.state.request_id = request_id
    start = time.monotonic()
    try:
        response: Response | None = None
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin is not None and origin not in settings.CORS_ORIGINS:
            response = JSONResponse(status_code=403, content={"detail": "Origem do pedido não permitida."})

        content_length = request.headers.get("content-length")
        if response is None and content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = -1
            if declared_size < 0:
                response = JSONResponse(status_code=400, content={"detail": "Content-Length inválido."})
            elif declared_size > settings.MAX_REQUEST_BODY_BYTES:
                response = JSONResponse(status_code=413, content={"detail": "Pedido demasiado grande."})
            else:
                response = await call_next(request)
        elif response is None:
            response = await call_next(request)
        assert response is not None
        duration_ms = (time.monotonic() - start) * 1000

        _apply_security_headers(request, response)
        response.headers[REQUEST_ID_HEADER] = request_id

        method = request.method
        http_requests_total.inc(method, status_class(response.status_code))
        http_request_duration_seconds_sum.inc(method, amount=duration_ms / 1000)
        http_request_duration_seconds_count.inc(method)

        logger.info(
            "request_completed method=%s path=%s status_code=%s duration_ms=%.1f",
            method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
    finally:
        # Reset LAST: everything above (including the log line) must run
        # while the context is still bound, or the log for this very
        # request would show request_id "-" instead of its own ID.
        reset_request_id(token)


@app.get("/health", tags=["system"])
def health() -> dict:
    """Liveness probe — process is up. Does not touch the database (a slow
    or down DB should make /ready fail, not make the process look dead)."""
    return {"status": "ok"}


@app.get("/ready", tags=["system"])
def ready() -> Response:
    """Readiness probe — verifies the database connection actually works.
    Cheap (a single SELECT 1, no app tables touched) and never leaks
    connection details on failure."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return JSONResponse(status_code=200, content={"status": "ready", "database": "connected"})
    except Exception:
        db_errors_total.inc()
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unreachable"})


@app.get("/metrics", tags=["system"], include_in_schema=False)
def metrics(request: Request) -> Response:
    """
    Disabled (404, indistinguishable from a route that doesn't exist) unless
    METRICS_TOKEN is configured, and even then requires it as a header — see
    app/core/config.py. Off by default so nobody accidentally ships a
    public, unauthenticated metrics endpoint.
    """
    if not settings.METRICS_TOKEN:
        raise HTTPException(status_code=404)
    if request.headers.get("x-metrics-token") != settings.METRICS_TOKEN:
        raise HTTPException(status_code=404)
    return PlainTextResponse(render_prometheus_text(), media_type="text/plain; version=0.0.4")


app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(clinics_router, prefix="/api/v1/clinics", tags=["clinics"])
app.include_router(patients_router, prefix="/api/v1/patients", tags=["patients"])
app.include_router(staff_router, prefix="/api/v1/staff", tags=["staff"])
app.include_router(appointments_router, prefix="/api/v1/appointments", tags=["appointments"])
app.include_router(consents_router, prefix="/api/v1", tags=["consents"])
app.include_router(medical_records_router, prefix="/api/v1", tags=["medical-records"])
app.include_router(medications_router, prefix="/api/v1", tags=["medications"])
app.include_router(notifications_router, prefix="/api/v1/notifications", tags=["notifications"])
