"""Add branching: novels.mode, roadmap tree, roadmap_choices, player_choices

Revision ID: f4a6c8d0e2b5
Revises: c2f8b7d1e4a9
Create Date: 2026-10-30 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a6c8d0e2b5'
down_revision: Union[str, Sequence[str], None] = 'c2f8b7d1e4a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. novels.mode — режим интерактивности (линейная / с выборами).
    op.add_column(
        'novels',
        sa.Column(
            'mode',
            sa.Enum('linear', 'interactive', name='novelmode', native_enum=False, length=32),
            nullable=False,
            server_default='linear',
        ),
    )

    # 2. roadmap: глобальный порядковый step_id перестаёт быть адресом —
    #    становится глубиной по пути (может повторяться между ветками).
    op.alter_column('roadmap', 'step_id', new_column_name='depth')

    # 3. roadmap: номер ветки (0 = истинная).
    op.add_column(
        'roadmap',
        sa.Column('branch_id', sa.Integer(), nullable=False, server_default='0'),
    )

    # 4. roadmap: ребро дерева — из какого шага пришли (NULL только у корня).
    op.add_column(
        'roadmap',
        sa.Column('parent_roadmap_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'roadmap_parent_roadmap_id_fkey',
        'roadmap', 'roadmap',
        ['parent_roadmap_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        op.f('ix_roadmap_parent_roadmap_id'), 'roadmap', ['parent_roadmap_id'], unique=False
    )

    # 5. Backfill: для уже существующих линейных новелл строим цепочку родительских
    #    ссылок по порядку depth — старые новеллы остаются рабочим истинным спайном.
    op.execute(
        """
        UPDATE roadmap r
        SET parent_roadmap_id = (
            SELECT p.id
            FROM roadmap p
            WHERE p.novel_id = r.novel_id AND p.depth = r.depth - 1
            ORDER BY p.id
            LIMIT 1
        )
        WHERE r.depth > 1
        """
    )

    # 6. roadmap_choices — варианты выбора (определение уровня шага роадмапа).
    op.create_table(
        'roadmap_choices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('roadmap_id', sa.Integer(), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('text', sa.String(), nullable=False),
        sa.Column('is_true', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('branch_direction', sa.Text(), nullable=True),
        sa.Column('next_roadmap_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_roadmap_choices_id'), 'roadmap_choices', ['id'], unique=False)
    op.create_index(op.f('ix_roadmap_choices_roadmap_id'), 'roadmap_choices', ['roadmap_id'], unique=False)
    op.create_foreign_key(
        'roadmap_choices_roadmap_id_fkey', 'roadmap_choices', 'roadmap',
        ['roadmap_id'], ['id'], ondelete='CASCADE',
    )
    op.create_foreign_key(
        'roadmap_choices_next_roadmap_id_fkey', 'roadmap_choices', 'roadmap',
        ['next_roadmap_id'], ['id'], ondelete='SET NULL',
    )

    # 7. player_choices — журнал выбранных вариантов (однозначный путь игрока).
    op.create_table(
        'player_choices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('novel_id', sa.Integer(), nullable=False),
        sa.Column('roadmap_choice_id', sa.Integer(), nullable=False),
        sa.Column('dialogue_line_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('roadmap_choice_id'),
    )
    op.create_index(op.f('ix_player_choices_id'), 'player_choices', ['id'], unique=False)
    op.create_index(op.f('ix_player_choices_novel_id'), 'player_choices', ['novel_id'], unique=False)
    op.create_foreign_key(
        'player_choices_novel_id_fkey', 'player_choices', 'novels',
        ['novel_id'], ['id'], ondelete='CASCADE',
    )
    op.create_foreign_key(
        'player_choices_roadmap_choice_id_fkey', 'player_choices', 'roadmap_choices',
        ['roadmap_choice_id'], ['id'], ondelete='CASCADE',
    )
    op.create_foreign_key(
        'player_choices_dialogue_line_id_fkey', 'player_choices', 'dialogue_lines',
        ['dialogue_line_id'], ['id'], ondelete='SET NULL',
    )

    # 8. dialogue_actions заменён на roadmap_choices.
    op.drop_table('dialogue_actions')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        'dialogue_actions',
        sa.Column('dialogue_line_id', sa.Integer(), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('text', sa.String(), nullable=False),
        sa.Column('next_roadmap_id', sa.Integer(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['dialogue_line_id'], ['dialogue_lines.id'], ),
        sa.ForeignKeyConstraint(['next_roadmap_id'], ['roadmap.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_dialogue_actions_dialogue_line_id'), 'dialogue_actions', ['dialogue_line_id'], unique=False)
    op.create_index(op.f('ix_dialogue_actions_id'), 'dialogue_actions', ['id'], unique=False)

    op.drop_table('player_choices')
    op.drop_table('roadmap_choices')
    op.drop_index(op.f('ix_roadmap_parent_roadmap_id'), table_name='roadmap')
    op.drop_constraint('roadmap_parent_roadmap_id_fkey', 'roadmap', type_='foreignkey')
    op.drop_column('roadmap', 'parent_roadmap_id')
    op.drop_column('roadmap', 'branch_id')
    op.alter_column('roadmap', 'depth', new_column_name='step_id')
    op.drop_column('novels', 'mode')
