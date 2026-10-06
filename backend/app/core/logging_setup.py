"""
Logging setup. Development: plain text, human-readable. Production: one
JSON object per line, safe for ingestion by any external log system
without extra parsing config.

Every log record gets a `request_id` field via RequestIdLogFilter, whether
or not the code that logged it bothered to pass one — this is what lets an
operator grep every log line for one request across every logger in the app.
"""
import json
import logging
from datetime import UTC, datetime

from app.core.request_context import get_request_id


class RequestIdLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """
    One JSON object per line. Only a fixed, known-safe set of fields is
    ever included — this formatter has no path by which an arbitrary
    object passed to `logger.info(..., extra={...})` could smuggle a
    secret into the output, because it never serializes `extra` blindly.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(*, debug: bool, json_output: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdLogFilter())

    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s")
        )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
