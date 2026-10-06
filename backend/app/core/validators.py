"""
Shared Pydantic field validators.

Extracted so every place that accepts a new password (patient self-registration,
staff creation, clinic onboarding, and any future "change password" endpoint)
enforces the exact same minimum bar — previously this check only existed on
the clinic onboarding schema, so patient and staff accounts could be created
with trivially weak passwords.
"""
COMMON_WEAK_PASSWORDS = {
    "password",
    "password1",
    "password123",
    "12345678",
    "123456789",
    "qwerty123",
    "letmein",
    "admin123",
    "abc12345",
}


def validate_password_strength(value: str) -> str:
    """
    Minimum bar, intentionally simple (length is already enforced by each
    schema's Field(min_length=8)): rejects a small, well-known blocklist of
    trivial passwords and passwords with no variety in characters at all.
    This is not meant to replace a proper breached-password check (e.g.
    HaveIBeenPwned k-anonymity API) — that's a reasonable v0.3 addition,
    not foundation hardening.
    """
    if value.lower() in COMMON_WEAK_PASSWORDS:
        raise ValueError("Password demasiado fraca.")
    if len(set(value)) <= 2:
        raise ValueError("Password demasiado fraca.")
    return value
