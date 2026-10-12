"""Run the scheduling background jobs.

    python -m app.jobs            # every JOBS_INTERVAL_SECONDS (default 60), until stopped
    python -m app.jobs --once     # one pass, then exit (cron, tests, manual runs)

Each pass sends the due appointment reminders, expires waiting-list offers and closes
waiting-list entries whose appointment has passed. Several runners are safe: a pass runs
only while it holds a database advisory lock, and every write is idempotent.
"""

import argparse
import logging
import os
import signal
import threading

from app.core.database import SessionLocal
from app.jobs import logger, run_once


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.jobs")
    parser.add_argument("--once", action="store_true", help="run one pass and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    interval = int(os.environ.get("JOBS_INTERVAL_SECONDS", "60"))
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    while True:
        try:
            with SessionLocal() as db:
                run_once(db)
        except Exception:  # keep running; the next pass retries (no clinical data in the log)
            logger.exception("scheduling_jobs pass failed")
            if args.once:
                raise
        if args.once or stop.wait(interval):
            break


if __name__ == "__main__":
    main()
