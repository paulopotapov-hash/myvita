"""
Synthetic two-clinic dataset for staging acceptance tests. Never run against real data.

    docker compose -f docker-compose.prod.yml exec \
        -e STAGING_SEED_CONFIRM=yes -e STAGING_SEED_PASSWORD='<generated>' \
        backend python -m scripts.seed_staging

The shared password is read from the environment and is never stored in Git.
The script is idempotent: identities that already exist are left untouched.
"""

import os
import sys
import uuid

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Clinic, StaffRole, User
from app.modules.clinics.schemas import ClinicOnboardingRequest
from app.modules.clinics.service import onboard_clinic
from app.modules.patients.schemas import PatientRegisterRequest
from app.modules.patients.service import create_patient_account
from app.modules.staff.schemas import StaffCreateRequest
from app.modules.staff.service import create_staff_member

CLINICS = {
    "a": {"staff": ["doctor", "nurse"], "patients": ["patient"]},
    "b": {"staff": ["doctor"], "patients": ["patient"]},
}


def _exists(db: Session, email: str) -> bool:
    return db.query(User).filter(User.email == email).first() is not None


def seed(db: Session, password: str, domain: str) -> list[str]:
    created: list[str] = []
    for key, spec in CLINICS.items():
        admin_email = f"admin-{key}@{domain}"
        if _exists(db, admin_email):
            clinic_id = str(db.query(User).filter(User.email == admin_email).one().clinic_id)
        else:
            clinic, _ = onboard_clinic(
                db,
                ClinicOnboardingRequest(
                    clinic_name=f"Staging Clinic {key.upper()}",
                    admin_full_name=f"Admin {key.upper()}",
                    admin_email=admin_email,
                    admin_password=password,
                ),
            )
            clinic_id = str(clinic.id)
            created.append(admin_email)
        for role in spec["staff"]:
            email = f"{role}-{key}@{domain}"
            if not _exists(db, email):
                create_staff_member(
                    db,
                    clinic_id,
                    StaffCreateRequest(
                        full_name=f"{role.title()} {key.upper()}",
                        email=email,
                        password=password,
                        staff_role=StaffRole(role),
                    ),
                )
                created.append(email)
        clinic_row = db.get(Clinic, uuid.UUID(clinic_id))
        assert clinic_row is not None  # just created or found via its admin above
        for name in spec["patients"]:
            email = f"{name}-{key}@{domain}"
            if not _exists(db, email):
                create_patient_account(
                    db,
                    clinic_row,
                    PatientRegisterRequest(
                        clinic_id=clinic_id,
                        full_name=f"{name.title()} {key.upper()}",
                        email=email,
                        password=password,
                    ),
                )
                created.append(email)
    return created


def main() -> int:
    if os.environ.get("STAGING_SEED_CONFIRM") != "yes":
        print("Refusing to run: set STAGING_SEED_CONFIRM=yes (staging/synthetic data only).", file=sys.stderr)
        return 1
    password = os.environ.get("STAGING_SEED_PASSWORD")
    if not password:
        print("Refusing to run: STAGING_SEED_PASSWORD is required.", file=sys.stderr)
        return 1
    domain = os.environ.get("STAGING_SEED_EMAIL_DOMAIN", "staging.example")
    with SessionLocal() as db:
        if db.query(Clinic).filter(~Clinic.name.like("Staging Clinic %")).first() is not None:
            print(
                "Refusing to run: non-seed clinics exist, this is not a synthetic-only database.",
                file=sys.stderr,
            )
            return 1
        created = seed(db, password, domain)
    print(f"Seed complete; {len(created)} identities created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
