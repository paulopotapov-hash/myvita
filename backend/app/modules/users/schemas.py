import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr

from app.models import StaffRole, UserRole


class AccountSummary(BaseModel):
    """Security state of one account in the admin's clinic.

    Patient e-mail addresses are omitted: the admin can act on a patient
    account (deactivate, issue a reset link) without seeing contact data
    the P4.1 matrix keeps from administrative roles.
    """

    id: uuid.UUID
    full_name: str
    role: UserRole
    staff_role: StaffRole | None
    email: EmailStr | None
    is_active: bool
    mfa_enabled: bool
    must_change_password: bool


class PasswordResetIssued(BaseModel):
    """Returned once. E-mailed when delivery is configured; otherwise (or if the
    e-mail failed) the admin hands the link to the person out of band."""

    user_id: uuid.UUID
    token: str
    expires_at: datetime
    delivery: Literal["sent", "failed", "disabled"] = "disabled"
