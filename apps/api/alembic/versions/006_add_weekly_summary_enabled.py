"""Add weekly_summary_enabled to users."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "006_add_weekly_summary_enabled"
down_revision: Union[str, None] = "005_add_auth_provider_subscription_tier"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("weekly_summary_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("users", "weekly_summary_enabled")
