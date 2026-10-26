"""add sound_asset_key to dialogue_lines

Revision ID: 8fc7cad0eeab
Revises: b7e4d9f0c3a6
Create Date: 2026-10-26 13:10:04.955775

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8fc7cad0eeab'
down_revision: Union[str, Sequence[str], None] = 'b7e4d9f0c3a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Эмбиент задника (asset_key .ogg) денормализуется в реплику, как и остальные
    # asset_key. Старые реплики получают NULL — бэкфилл не нужен.
    op.add_column('dialogue_lines', sa.Column('sound_asset_key', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('dialogue_lines', 'sound_asset_key')
