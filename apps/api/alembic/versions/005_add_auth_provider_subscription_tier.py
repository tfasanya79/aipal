"""Add auth_provider and subscription_tier to users."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_add_auth_provider_subscription_tier"
down_revision: Union[str, None] = "001_initial_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("auth_provider", sa.String(length=32), nullable=False, server_default="magic_link"),
    )
    op.add_column(
        "users",
        sa.Column("subscription_tier", sa.String(length=32), nullable=False, server_default="free"),
    )


def downgrade() -> None:
    op.drop_column("users", "subscription_tier")
    op.drop_column("users", "auth_provider")
