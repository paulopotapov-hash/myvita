"""Portuguese personal identifiers: validation and masking.

NIF, NISS and the SNS user number identify a person. They are sensitive:
the API returns them masked (last three digits only), the full value only
through the audited reveal endpoint, and they never go to logs or to audit
metadata (only the names of changed fields do).
"""

import re

POSTAL_CODE_PATTERN = re.compile(r"^\d{4}-\d{3}$")
_NIF_PATTERN = re.compile(r"^\d{9}$")
_NISS_PATTERN = re.compile(r"^[12]\d{10}$")
_SNS_PATTERN = re.compile(r"^\d{9}$")
_NISS_WEIGHTS = (29, 23, 19, 17, 13, 11, 7, 5, 3, 2)
VISIBLE_DIGITS = 3


def is_valid_nif(value: str) -> bool:
    """Número de Identificação Fiscal: 9 digits, modulo-11 check digit."""
    if not _NIF_PATTERN.match(value):
        return False
    total = sum(int(digit) * weight for digit, weight in zip(value[:8], range(9, 1, -1), strict=True))
    remainder = total % 11
    check = 0 if remainder < 2 else 11 - remainder
    return check == int(value[8])


def is_valid_niss(value: str) -> bool:
    """Número de Identificação da Segurança Social: 11 digits starting 1 or 2, weighted check digit."""
    if not _NISS_PATTERN.match(value):
        return False
    total = sum(int(digit) * weight for digit, weight in zip(value[:10], _NISS_WEIGHTS, strict=True))
    return 9 - total % 10 == int(value[10])


def is_valid_sns_number(value: str) -> bool:
    """Número de utente do SNS: 9 digits (no public check-digit rule)."""
    return bool(_SNS_PATTERN.match(value))


def is_valid_postal_code(value: str) -> bool:
    return bool(POSTAL_CODE_PATTERN.match(value))


def mask(value: str | None) -> str | None:
    """Only the last three characters are ever shown without the audited reveal."""
    if not value:
        return None
    visible = value[-VISIBLE_DIGITS:]
    return "•" * max(len(value) - VISIBLE_DIGITS, 0) + visible
