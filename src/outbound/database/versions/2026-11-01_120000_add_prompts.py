"""Add prompts table (versioned prompt templates) and novels.prompt_variant

Revision ID: e7b4a2d9c0f5
Revises: f4a6c8d0e2b5
Create Date: 2026-11-01 12:00:00.000000

"""
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from src.core.novels.services.generation.prompts.defaults import DEFAULT_PROMPTS


# revision identifiers, used by Alembic.
revision: str = 'e7b4a2d9c0f5'
down_revision: Union[str, Sequence[str], None] = 'f4a6c8d0e2b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. novels.prompt_variant — набор промптов (default, nsfw, …).
    op.add_column(
        'novels',
        sa.Column(
            'prompt_variant',
            sa.String(),
            nullable=False,
            server_default='default',
        ),
    )

    # 2. prompts — версионируемые шаблоны промптов (append-only).
    op.create_table(
        'prompts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('variant', sa.String(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('system_template', sa.Text(), nullable=False),
        sa.Column('user_template', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key', 'variant', 'version', name='uq_prompts_key_variant_version'),
    )
    op.create_index(op.f('ix_prompts_id'), 'prompts', ['id'], unique=False)
    op.create_index(op.f('ix_prompts_key'), 'prompts', ['key'], unique=False)
    op.create_index(op.f('ix_prompts_variant'), 'prompts', ['variant'], unique=False)

    # 3. Сид версии 1 (вариант default) из встроенных дефолтов.
    prompts_table = sa.table(
        'prompts',
        sa.column('key', sa.String()),
        sa.column('variant', sa.String()),
        sa.column('version', sa.Integer()),
        sa.column('system_template', sa.Text()),
        sa.column('user_template', sa.Text()),
        sa.column('is_active', sa.Boolean()),
        sa.column('created_at', sa.DateTime(timezone=True)),
        sa.column('updated_at', sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        prompts_table,
        [
            {
                'key': key,
                'variant': 'default',
                'version': 1,
                'system_template': template.system,
                'user_template': template.user,
                'is_active': True,
                'created_at': now,
                'updated_at': now,
            }
            for key, template in DEFAULT_PROMPTS.items()
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_prompts_variant'), table_name='prompts')
    op.drop_index(op.f('ix_prompts_key'), table_name='prompts')
    op.drop_index(op.f('ix_prompts_id'), table_name='prompts')
    op.drop_table('prompts')
    op.drop_column('novels', 'prompt_variant')
