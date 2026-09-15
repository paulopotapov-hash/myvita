from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine

app = FastAPI(
    title=settings.APP_NAME,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,  # required for httpOnly cookie auth across origins
    allow_methods=["*"],
    allow_headers=["*"],
)


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


from app.modules.appointments.router import router as appointments_router
from app.modules.auth.router import router as auth_router
from app.modules.clinics.router import router as clinics_router
from app.modules.patients.router import router as patients_router
from app.modules.staff.router import router as staff_router

app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(clinics_router, prefix="/api/v1/clinics", tags=["clinics"])
app.include_router(patients_router, prefix="/api/v1/patients", tags=["patients"])
app.include_router(staff_router, prefix="/api/v1/staff", tags=["staff"])
app.include_router(appointments_router, prefix="/api/v1/appointments", tags=["appointments"])
