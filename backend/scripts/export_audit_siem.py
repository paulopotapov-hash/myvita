"""
Export new audit events to the configured SIEM endpoint (see docs/audit-logging.md).

    python scripts/export_audit_siem.py [--max-batches N] [--until ISO8601] [--dry-run]

Runs out-of-band (cron / compose one-shot). Exits 0 when all available events
were delivered, 2 when SIEM is disabled, 1 when the sink rejected a batch — in
which case the cursor file still points at the last accepted event and the
next run resumes from there (at-least-once; consumers deduplicate on `id`).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.audit_export import (  # noqa: E402
    SiemDisabledError,
    SiemExportError,
    export_audit_events,
    load_cursor,
    save_cursor,
    sink_from_settings,
)
from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402

logger = logging.getLogger("myvita.audit.siem")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--max-batches", type=int, default=50, help="Upper bound of batches per run (default 50)."
    )
    parser.add_argument(
        "--until", type=datetime.fromisoformat, default=None, help="Only export events up to this UTC time."
    )
    parser.add_argument("--cursor-file", type=Path, default=Path(settings.SIEM_CURSOR_FILE))
    parser.add_argument(
        "--dry-run", action="store_true", help="Count exportable events; send nothing, save nothing."
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    try:
        sink = sink_from_settings()
    except SiemDisabledError as exc:
        logger.info("%s", exc)
        return 2

    class _Counting:
        sent = 0

        def send(self, events):  # type: ignore[no-untyped-def]
            self.sent += len(events)

    cursor = load_cursor(args.cursor_file)
    db = SessionLocal()
    try:
        report = export_audit_events(
            db,
            _Counting() if args.dry_run else sink,
            cursor=cursor,
            batch_size=settings.SIEM_BATCH_SIZE,
            max_batches=args.max_batches,
            until=args.until,
            on_cursor=None if args.dry_run else (lambda c: save_cursor(args.cursor_file, c)),
        )
    except SiemExportError as exc:
        logger.error("Export stopped: %s (cursor left at last accepted event)", exc)
        return 1
    finally:
        db.close()
    logger.info(
        "Export %s: %d events in %d batches; cursor=%s",
        "dry-run" if args.dry_run else "complete",
        report.events,
        report.batches,
        report.cursor.to_json() if report.cursor else "none",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
