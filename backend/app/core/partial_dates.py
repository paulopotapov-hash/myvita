"""Partial dates (decision D5): "2010", "2010-03" or "2010-03-12".

Stored as the first day of the period plus its precision, so the database can
order and compare them while the UI shows "2010", "março 2010" or "12/03/2010".
"""

import re
from datetime import date

from app.models.clinical_history import DatePrecision

_PATTERN = re.compile(r"^(?P<year>\d{4})(?:-(?P<month>\d{2})(?:-(?P<day>\d{2}))?)?$")
MIN_YEAR = 1900


class PartialDateError(ValueError):
    pass


def parse_partial_date(value: str, *, today: date | None = None) -> tuple[date, DatePrecision]:
    match = _PATTERN.match(value.strip())
    if match is None:
        raise PartialDateError("Usa o formato AAAA, AAAA-MM ou AAAA-MM-DD.")
    year = int(match["year"])
    month = int(match["month"]) if match["month"] else 1
    day = int(match["day"]) if match["day"] else 1
    try:
        parsed = date(year, month, day)
    except ValueError as exc:
        raise PartialDateError("Data inválida.") from exc
    if year < MIN_YEAR:
        raise PartialDateError(f"O ano tem de ser {MIN_YEAR} ou posterior.")
    if parsed > (today or date.today()):
        raise PartialDateError("A data não pode ser no futuro.")
    precision = DatePrecision.DAY if match["day"] else DatePrecision.MONTH if match["month"] else DatePrecision.YEAR
    return parsed, precision


def format_partial_date(value: date | None, precision: DatePrecision | None) -> str | None:
    """The API form of a stored partial date (the UI turns it into "março 2010" etc.)."""
    if value is None or precision is None:
        return None
    if precision == DatePrecision.YEAR:
        return f"{value.year:04d}"
    if precision == DatePrecision.MONTH:
        return f"{value.year:04d}-{value.month:02d}"
    return value.isoformat()
