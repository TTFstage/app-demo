"""Add one-to-one bikes and their tracking sessions.

Revision ID: b784e3d2c918
Revises: d4a7c9012b3e
Create Date: 2026-09-23
"""

import sqlalchemy as sa
from alembic import op


revision = 'b784e3d2c918'
down_revision = 'd4a7c9012b3e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bikes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bike_id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('total_km', sa.Float(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bike_id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_table(
        'bike_tracking',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bike_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('total_km', sa.Float(), nullable=False, server_default='0'),
        sa.Column('gpx_path', sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(['bike_id'], ['bikes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('bike_tracking')
    op.drop_table('bikes')
