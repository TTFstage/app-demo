"""Add persistent user preferences and auditable SOS delivery records.

Revision ID: f42c91a7d011
Revises: c51a9f0e42d1
Create Date: 2026-09-18
"""

import sqlalchemy as sa
from alembic import op

revision = 'f42c91a7d011'
down_revision = 'c51a9f0e42d1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_preferences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('telemetry_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('fall_detection_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('sos_notifications_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('browser_notifications_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('high_accuracy_gps', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('map_default_overlays', sa.String(length=120), nullable=False, server_default='stations,bicycle_repair'),
        sa.Column('appearance', sa.String(length=16), nullable=False, server_default='system'),
        sa.Column('onboarding_completed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_index('ix_user_preferences_user_id', 'user_preferences', ['user_id'], unique=True)

    op.create_table(
        'sos_alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(length=255), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('delivery_status', sa.String(length=32), nullable=False, server_default='not_configured'),
        sa.Column('delivery_detail', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sos_alerts_user_id', 'sos_alerts', ['user_id'], unique=False)


def downgrade():
    op.drop_index('ix_sos_alerts_user_id', table_name='sos_alerts')
    op.drop_table('sos_alerts')
    op.drop_index('ix_user_preferences_user_id', table_name='user_preferences')
    op.drop_table('user_preferences')
