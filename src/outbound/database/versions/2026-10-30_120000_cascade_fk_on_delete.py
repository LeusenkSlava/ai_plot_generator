"""Cascade ON DELETE for generation FK graph

Revision ID: c2f8b7d1e4a9
Revises: 8fc7cad0eeab
Create Date: 2026-10-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c2f8b7d1e4a9'
down_revision: Union[str, Sequence[str], None] = '8fc7cad0eeab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Единственный источник истины про удаление потомков — СУБД (ON DELETE CASCADE).
# Раньше компенсация саги чистила детей вручную сырым SQL в правильном порядке;
# теперь удаление родителя (novels / scenes) каскадно удаляет всё дерево.
# next_roadmap_id — опциональная ссылка, поэтому SET NULL, а не CASCADE.
_CASCADE_FKS = {
    'characters': [
        ('characters_novel_id_fkey', 'novels', ['novel_id'], ['id']),
    ],
    'roadmap': [
        ('roadmap_novel_id_fkey', 'novels', ['novel_id'], ['id']),
    ],
    'scenes': [
        ('scenes_roadmap_id_fkey', 'roadmap', ['roadmap_id'], ['id']),
    ],
    'dialogue_lines': [
        ('dialogue_lines_novel_id_fkey', 'novels', ['novel_id'], ['id']),
        ('dialogue_lines_scene_id_fkey', 'scenes', ['scene_id'], ['id']),
        ('dialogue_lines_character_id_fkey', 'characters', ['character_id'], ['id']),
    ],
    'dialogue_actions': [
        ('dialogue_actions_dialogue_line_id_fkey', 'dialogue_lines', ['dialogue_line_id'], ['id']),
    ],
}

_SET_NULL_FKS = {
    'dialogue_actions': [
        ('dialogue_actions_next_roadmap_id_fkey', 'roadmap', ['next_roadmap_id'], ['id']),
    ],
}


def upgrade() -> None:
    """Upgrade schema."""
    for table, fks in _CASCADE_FKS.items():
        for name, ref_table, local_cols, remote_cols in fks:
            op.drop_constraint(name, table, type_='foreignkey')
            op.create_foreign_key(
                name, table, ref_table, local_cols, remote_cols, ondelete='CASCADE'
            )
    for table, fks in _SET_NULL_FKS.items():
        for name, ref_table, local_cols, remote_cols in fks:
            op.drop_constraint(name, table, type_='foreignkey')
            op.create_foreign_key(
                name, table, ref_table, local_cols, remote_cols, ondelete='SET NULL'
            )


def downgrade() -> None:
    """Downgrade schema."""
    for table, fks in _CASCADE_FKS.items():
        for name, ref_table, local_cols, remote_cols in fks:
            op.drop_constraint(name, table, type_='foreignkey')
            op.create_foreign_key(name, table, ref_table, local_cols, remote_cols)
    for table, fks in _SET_NULL_FKS.items():
        for name, ref_table, local_cols, remote_cols in fks:
            op.drop_constraint(name, table, type_='foreignkey')
            op.create_foreign_key(name, table, ref_table, local_cols, remote_cols)
