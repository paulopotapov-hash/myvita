"""
Request ID: generated (or validated-and-reused) once per request, made
available to structured logging via a ContextVar, and echoed back in the
response so a client/support ticket can reference the exact request.
"""
import contextvars
import re
import uuid

REQUEST_ID_HEADER = "X-Request-ID"

# Bounded length and a narrow character set: this value gets logged and
# echoed back verbatim, so it must never become a vector for log injection
# or for smuggling arbitrary/oversized data through a header nobody
# expected to carry a payload. A client-supplied ID outside this shape is
# treated as absent — we generate our own instead of trying to sanitize it.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

_current_request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "myvita_request_id", default="-"
)


def get_request_id() -> str:
    """Current request's ID for logging. Returns "-" outside a request
    (e.g. at import time, or in a background task with no request context)."""
    return _current_request_id.get()


def new_request_id(client_supplied: str | None) -> str:
    """Reuse a client-supplied ID if it's well-formed; otherwise mint a
    fresh one. A UUID4's hex form is used — random, not sequential/guessable,
    and carries no information about the user, time, or server internals."""
    if client_supplied and _VALID_REQUEST_ID.match(client_supplied):
        return client_supplied
    return uuid.uuid4().hex


def bind_request_id(request_id: str) -> contextvars.Token[str]:
    return _current_request_id.set(request_id)


def reset_request_id(token: contextvars.Token[str]) -> None:
    _current_request_id.reset(token)
