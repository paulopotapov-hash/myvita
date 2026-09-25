"""Shared API schema defaults for untrusted request payloads."""

from pydantic import BaseModel, ConfigDict


class RequestModel(BaseModel):
    """Reject unknown fields instead of silently accepting client mistakes.

    This also prevents security-sensitive server-derived fields such as
    ``clinic_id`` or ``role`` from appearing to have been accepted when the
    API actually ignores them.
    """

    model_config = ConfigDict(extra="forbid")
