"""add_rooms

Revision ID: b283accb8899
Revises:
Create Date: 2026-02-12 14:17:13.884366
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b283accb8899'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('rooms',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('room_camera_mappings',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('room_id', sa.Integer(), nullable=False),
    sa.Column('camera_id', sa.String(length=50), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('room_id', 'camera_id', name='uq_room_camera')
    )
    with op.batch_alter_table('room_camera_mappings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_room_camera_mappings_room_id'), ['room_id'], unique=False)

    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('room_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_events_room_id'), ['room_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_events_room_id'))
        batch_op.drop_column('room_id')

    with op.batch_alter_table('room_camera_mappings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_room_camera_mappings_room_id'))

    op.drop_table('room_camera_mappings')
    op.drop_table('rooms')
