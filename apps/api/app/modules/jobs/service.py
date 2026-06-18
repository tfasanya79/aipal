"""Durable job queue (Postgres-backed, same VM worker)."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import Job, utc_now

log = logging.getLogger("aipal.jobs")

HANDLERS: dict[str, str] = {
    "noop": "Built-in no-op for health checks",
}


async def enqueue(
    db: AsyncSession,
    job_type: str,
    payload: dict | None = None,
    *,
    run_after: datetime | None = None,
    max_attempts: int = 3,
) -> Job:
    job = Job(
        job_type=job_type,
        payload=payload or {},
        run_after=run_after or utc_now(),
        max_attempts=max_attempts,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def claim_next(db: AsyncSession) -> Job | None:
    now = utc_now()
    result = await db.execute(
        select(Job)
        .where(Job.status == "pending", Job.run_after <= now, Job.attempts < Job.max_attempts)
        .order_by(Job.run_after.asc(), Job.id.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = result.scalar_one_or_none()
    if not job:
        return None
    job.status = "running"
    job.started_at = now
    job.attempts += 1
    await db.commit()
    await db.refresh(job)
    return job


async def complete(db: AsyncSession, job_id: int) -> None:
    await db.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status="done", finished_at=utc_now(), last_error=None)
    )
    await db.commit()


async def fail(db: AsyncSession, job: Job, error: str) -> None:
    status = "pending" if job.attempts < job.max_attempts else "failed"
    await db.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(status=status, last_error=error[:2000], finished_at=utc_now() if status == "failed" else None)
    )
    await db.commit()


async def run_job(db: AsyncSession, job: Job) -> None:
    if job.job_type == "noop":
        log.info("noop job %s ok", job.id)
        return
    raise NotImplementedError(f"No handler for job_type={job.job_type}")
