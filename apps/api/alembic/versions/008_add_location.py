"""Add city and country_code to users."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "008_add_location"
down_revision: Union[str, None] = "007_add_tts_voice"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("city", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("country_code", sa.String(8), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "country_code")
    op.drop_column("users", "city")
