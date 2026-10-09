"""Audit metadata policy: the allowlist in app/core/audit.py is the only gate
between application code and the persisted `metadata` column, so (1) every key
the application actually passes must be listed — otherwise it is silently
dropped and an investigation loses context — and (2) the sanitiser must drop
anything that could carry a secret or clinical content."""

import ast
import logging
import uuid
from pathlib import Path

import pytest

from app.core.audit import _SENSITIVE_KEY_PATTERN, ALLOWED_METADATA_KEYS, sanitize_metadata

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _metadata_dict_keys_in(path: Path) -> set[str]:
    """String keys of every dict literal passed as `metadata=` in a call."""
    keys: set[str] = set()
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg == "metadata" and isinstance(keyword.value, ast.Dict):
                for key in keyword.value.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        keys.add(key.value)
    return keys


def test_every_metadata_key_used_by_the_application_is_allowlisted():
    used: dict[str, set[str]] = {}
    for path in APP_DIR.rglob("*.py"):
        for key in _metadata_dict_keys_in(path):
            used.setdefault(key, set()).add(str(path.relative_to(APP_DIR)))
    # Keys the code passes via `**extra` dicts rather than literals.
    used.setdefault("expires_at", {"account_recovery.py", "modules/users/router.py"})
    used.setdefault("actor_staff_role", {"core/audit.py"})
    missing = {key: sorted(files) for key, files in used.items() if key not in ALLOWED_METADATA_KEYS}
    assert not missing, f"metadata keys used but not allowlisted (would be silently dropped): {missing}"


def test_no_allowlisted_key_is_rejected_by_the_sensitive_pattern():
    rejected = sorted(key for key in ALLOWED_METADATA_KEYS if _SENSITIVE_KEY_PATTERN.search(key))
    assert rejected == [], f"allowlisted keys that the sensitive-key pattern would drop anyway: {rejected}"


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "hashed_password",
        "token",
        "reset_token",
        "session_token",
        "csrf",
        "cookie",
        "authorization",
        "api_key",
        "secret",
        "body",
        "content",
        "message",
        "message_body",
        "record",
        "note",
        "text",
        "password_hash",
    ],
)
def test_sanitize_drops_secret_and_clinical_content_keys(key, caplog):
    with caplog.at_level(logging.WARNING, logger="myvita.audit"):
        assert sanitize_metadata({key: "x", "path": "/p"}) == {"path": "/p"}
    assert "Dropping disallowed audit metadata key" in caplog.text


def test_sanitize_keeps_privacy_preserving_identity_and_lifecycle_keys():
    staff_id = uuid.uuid4()
    clean = sanitize_metadata(
        {
            "email_masked": "n***@example.com",
            "email_fingerprint": "0123456789abcdef",
            "mfa": True,
            "stage": "enable",
            "forced": False,
            "recovery_codes_remaining": 7,
            "staff_id": staff_id,
            "ticket": "HELP-1234",
            "initial_message": True,
            "required_roles": ["staff", "clinic_admin"],
            "filters": {"action": "login_failure", "password": "must-not-survive"},
        }
    )
    assert clean == {
        "email_masked": "n***@example.com",
        "email_fingerprint": "0123456789abcdef",
        "mfa": True,
        "stage": "enable",
        "forced": False,
        "recovery_codes_remaining": 7,
        "staff_id": str(staff_id),
        "ticket": "HELP-1234",
        "initial_message": True,
        "required_roles": ["staff", "clinic_admin"],
        "filters": {"action": "login_failure"},
    }


def test_sanitize_bounds_sizes_and_rejects_model_instances():
    class NotAScalar:
        pass

    clean = sanitize_metadata({"reason": "r" * 500, "required_roles": list(range(100)), "path": NotAScalar()})
    assert clean is not None
    assert len(clean["reason"]) == 200
    assert len(clean["required_roles"]) == 25
    assert "path" not in clean
    assert sanitize_metadata({}) is None
    assert sanitize_metadata({"password": "x"}) is None
