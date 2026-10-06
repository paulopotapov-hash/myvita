"""
Operator recovery for clinic administrators (docs/security/account-lifecycle.md).

A clinic admin cannot manage another admin's credentials in the app (that
would let one admin take over another's identity), and nobody can manage
their own credentials once locked out. This tool is the controlled path for
those cases. It runs on the production host, inside the backend container,
by an operator acting on a verified, ticketed request:

    python -m app.account_recovery issue-password-reset --email ADMIN --ticket REF
    python -m app.account_recovery reset-mfa --email ADMIN --ticket REF

Guard rails:
- only accounts with role clinic_admin (staff and patients are recovered by
  their clinic admin in the app);
- the account must be active;
- a ticket reference is mandatory and is written to the audit trail;
- every action is audited with no actor (it did not come from a session)
  and `via=operator`;
- the reset token is printed exactly once, to stdout, and never audited or
  logged. Hand the link over out of band, never through the ticket itself.
"""

import argparse
import sys

from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.database import SessionLocal
from app.models import AuditAction, AuditResult, User, UserMfa, UserRole
from app.modules.auth import mfa_service, password_reset

RESET_LINK_PATH = "/redefinir-palavra-passe#token="


class RecoveryError(RuntimeError):
    pass


def _target(db: Session, email: str) -> User:
    user = db.query(User).filter(User.email_matches(email)).first()
    if user is None:
        raise RecoveryError("No account with that e-mail address.")
    if user.role != UserRole.CLINIC_ADMIN:
        raise RecoveryError("Only clinic_admin accounts are recovered here; the clinic admin handles everyone else.")
    if not user.is_active:
        raise RecoveryError("The account is deactivated; reactivate it through another clinic admin first.")
    return user


def _validate_ticket(ticket: str) -> str:
    ticket = ticket.strip()
    if not 3 <= len(ticket) <= 64:
        raise RecoveryError("--ticket must be a 3-64 character reference to the verified request.")
    return ticket


def _audit(action: AuditAction, user: User, ticket: str, metadata: dict | None = None) -> None:
    record_audit_event(
        action=action,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        resource_type="user",
        resource_id=user.id,
        metadata={"via": "operator", "ticket": ticket, "target_role": user.role.value, **(metadata or {})},
    )


def issue_admin_password_reset(db: Session, email: str, ticket: str) -> tuple[User, str]:
    ticket = _validate_ticket(ticket)
    user = _target(db, email)
    token, expires_at = password_reset.issue(db, user, issued_by=None)
    _audit(AuditAction.PASSWORD_RESET_ISSUED, user, ticket, {"expires_at": expires_at.isoformat()})
    return user, token


def reset_admin_mfa(db: Session, email: str, ticket: str) -> User:
    ticket = _validate_ticket(ticket)
    user = _target(db, email)
    if db.query(UserMfa).filter(UserMfa.user_id == user.id).first() is None:
        raise RecoveryError("This account has no MFA enrolment to reset.")
    mfa_service.remove_enrolment(db, user)
    _audit(AuditAction.MFA_RESET, user, ticket)
    return user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.account_recovery", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("issue-password-reset", "reset-mfa"):
        command = sub.add_parser(name)
        command.add_argument("--email", required=True)
        command.add_argument("--ticket", required=True, help="Reference of the verified recovery request.")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        if args.command == "issue-password-reset":
            _, token = issue_admin_password_reset(db, args.email, args.ticket)
            print("One-time reset link path (append to the public https:// origin; valid once):")
            print(f"{RESET_LINK_PATH}{token}")
        else:
            reset_admin_mfa(db, args.email, args.ticket)
            print("MFA removed and all sessions revoked. The admin must enrol MFA again at next login.")
    except RecoveryError as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 2
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
