"""generation_jobs.job_id: string -> integer

Revision ID: 7a3e9b1d4c20
Revises: 1c00dc2d5f41
Create Date: 2026-10-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a3e9b1d4c20'
down_revision: Union[str, Sequence[str], None] = '1c00dc2d5f41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Нечисловые job_id старого формата (request_id) перевести нельзя — удаляем
    op.execute("DELETE FROM generation_jobs WHERE job_id !~ '^[0-9]+$'")
    op.alter_column(
        'generation_jobs',
        'job_id',
        existing_type=sa.String(),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using='job_id::integer',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'generation_jobs',
        'job_id',
        existing_type=sa.Integer(),
        type_=sa.String(),
        existing_nullable=False,
        postgresql_using='job_id::varchar',
    )
