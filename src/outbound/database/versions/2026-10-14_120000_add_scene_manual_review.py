"""Add scene manual review flags

Revision ID: c3f7a1b9d2e5
Revises: 7b3d5e8f9a1c
Create Date: 2026-10-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f7a1b9d2e5'
down_revision: Union[str, Sequence[str], None] = '7b3d5e8f9a1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # needs_review: сцена не прошла смысловую проверку соответствия шагу роадмапа
    # даже после ретраев и требует ручного вмешательства.
    op.add_column(
        'scenes',
        sa.Column('needs_review', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # review_reason: причина расхождения (пишется вместе с needs_review и в llm_logs).
    op.add_column(
        'scenes',
        sa.Column('review_reason', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('scenes', 'review_reason')
    op.drop_column('scenes', 'needs_review')
