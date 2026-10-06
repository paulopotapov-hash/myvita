"""
Import every model here so Base.metadata is fully populated for Alembic
autogenerate, and so `from app.models import User` etc. works elsewhere.
"""

from app.models.appointment import Appointment, AppointmentStatus  # noqa: F401
from app.models.audit_log import AuditAction, AuditLog, AuditResult  # noqa: F401
from app.models.clinic import Clinic  # noqa: F401
from app.models.consent import Consent, ConsentStatus, ConsentType  # noqa: F401
from app.models.medical_record import MedicalRecord, MedicalRecordRevision  # noqa: F401
from app.models.medication import Medication, MedicationStatus  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.patient import Patient  # noqa: F401
from app.models.staff import Staff, StaffRole  # noqa: F401
from app.models.user import User, UserRole  # noqa: F401
