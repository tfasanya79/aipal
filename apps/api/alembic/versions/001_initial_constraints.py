"""Initial constraints, indexes, and jobs table."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_constraints"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_job_type", "jobs", ["job_type"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_run_after", "jobs", ["run_after"])

    op.create_index("ix_tasks_user_status", "tasks", ["user_id", "status"])
    op.create_index("ix_tasks_user_due", "tasks", ["user_id", "due_at"])
    op.create_index("ix_conversation_turns_user_session", "conversation_turns", ["user_id", "session_id"])
    op.create_index("ix_session_events_user_session", "session_events", ["user_id", "session_id"])

    op.execute(
        "ALTER TABLE tasks ADD CONSTRAINT ck_tasks_status "
        "CHECK (status IN ('planned','in_progress','done','deferred','skipped'))"
    )
    op.create_unique_constraint("uq_calendar_user_external", "calendar_events_cache", ["user_id", "external_id"])
    op.create_unique_constraint("uq_integration_user_provider", "integration_tokens", ["user_id", "provider"])


def downgrade() -> None:
    op.drop_constraint("uq_integration_user_provider", "integration_tokens", type_="unique")
    op.drop_constraint("uq_calendar_user_external", "calendar_events_cache", type_="unique")
    op.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS ck_tasks_status")
    op.drop_index("ix_session_events_user_session", table_name="session_events")
    op.drop_index("ix_conversation_turns_user_session", table_name="conversation_turns")
    op.drop_index("ix_tasks_user_due", table_name="tasks")
    op.drop_index("ix_tasks_user_status", table_name="tasks")
    op.drop_index("ix_jobs_run_after", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_job_type", table_name="jobs")
    op.drop_table("jobs")
