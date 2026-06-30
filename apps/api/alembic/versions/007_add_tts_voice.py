"""Add tts_voice to users."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "007_add_tts_voice"
down_revision: Union[str, None] = "006_add_weekly_summary_enabled"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("tts_voice", sa.String(32), nullable=False, server_default="aria"),
    )


def downgrade() -> None:
    op.drop_column("users", "tts_voice")
