import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.schemas import RequestModel
from app.core.validators import NormalizedEmail, validate_password_strength
from app.models.staff import StaffRole
from app.models.user import UserRole


class LoginRequest(RequestModel):
    email: NormalizedEmail
    password: str = Field(min_length=1, max_length=128)


class PasswordChangeRequest(RequestModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_not_trivial(cls, value: str) -> str:
        return validate_password_strength(value)


PendingAccountAction = Literal["password_change", "mfa_verification", "mfa_setup"]


class UserPublic(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    clinic_id: uuid.UUID | None
    staff_role: StaffRole | None = None
    patient_id: uuid.UUID | None = None
    must_change_password: bool = False
    mfa_enabled: bool = False
    mfa_required: bool = False
    # What the user must do before anything else works, if anything.
    pending_action: PendingAccountAction | None = None

    model_config = {"from_attributes": True}


class MfaChallengeResponse(BaseModel):
    """Password accepted; a second factor is required to finish logging in."""

    mfa_required: Literal[True] = True


class MfaCodeRequest(RequestModel):
    # 6-digit TOTP code, or a recovery code ("abcde-fghij") where allowed.
    code: str = Field(min_length=6, max_length=32)


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MfaRecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class MfaDisableRequest(RequestModel):
    current_password: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=32)


class PasswordResetConfirmRequest(RequestModel):
    token: str = Field(min_length=40, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_not_trivial(cls, value: str) -> str:
        return validate_password_strength(value)


class PasswordResetRequest(RequestModel):
    email: NormalizedEmail


class GenericMessage(BaseModel):
    detail: str
