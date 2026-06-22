#!/usr/bin/env python3
"""Poll Postgres jobs table and execute handlers (same VM as API)."""

import asyncio
import logging
import signal

from app.modules.jobs import service as job_svc
from app.shared.db import async_session, init_db

log = logging.getLogger("aipal.worker")
POLL_SECONDS = 5
_stop = False


def _handle_signal(*_args):
    global _stop
    _stop = True


async def process_one() -> bool:
    async with async_session() as db:
        job = await job_svc.claim_next(db)
        if not job:
            return False
        try:
            await job_svc.run_job(db, job)
            await job_svc.complete(db, job.id)
            log.info("job %s type=%s done", job.id, job.job_type)
        except Exception as exc:
            log.exception("job %s failed", job.id)
            await job_svc.fail(db, job, str(exc))
    return True


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    await init_db()
    log.info("aipal worker started (poll=%ss)", POLL_SECONDS)
    while not _stop:
        worked = await process_one()
        if not worked:
            await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
