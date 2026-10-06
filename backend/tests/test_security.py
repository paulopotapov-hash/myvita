from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models import Clinic, User, UserRole


def test_password_is_hashed_not_stored_plain():
    hashed = hash_password("SenhaForte123!")
    assert hashed != "SenhaForte123!"
    assert hashed.startswith("$argon2")


def test_verify_password_correct_and_incorrect():
    hashed = hash_password("SenhaForte123!")
    assert verify_password("SenhaForte123!", hashed) is True
    assert verify_password("senha-errada", hashed) is False


def _make_user(db, epoch=0):
    clinic = Clinic(name="C", nif="123")
    db.add(clinic)
    db.flush()
    user = User(
        email="user@test.pt",
        full_name="Test User",
        hashed_password=hash_password("x"),
        role=UserRole.PATIENT,
        clinic_id=clinic.id,
        token_epoch=epoch,
    )
    db.add(user)
    db.commit()
    return user


def test_token_roundtrip_contains_expected_claims(db_session):
    user = _make_user(db_session)
    token = create_access_token(user)
    payload = decode_access_token(token)

    assert payload["sub"] == str(user.id)
    assert payload["clinic_id"] == str(user.clinic_id)
    assert payload["role"] == "patient"
    assert payload["epoch"] == 0


def test_bumping_token_epoch_invalidates_old_tokens_conceptually(db_session):
    """
    This test documents the invalidation mechanism at the token level.
    The full end-to-end check (old cookie rejected by get_current_user)
    belongs in an integration test once the auth router/endpoints exist.
    """
    user = _make_user(db_session, epoch=0)
    old_token = create_access_token(user)
    old_payload = decode_access_token(old_token)

    user.token_epoch = 1
    db_session.commit()

    assert old_payload["epoch"] != user.token_epoch
