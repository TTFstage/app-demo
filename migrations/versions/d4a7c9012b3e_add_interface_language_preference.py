"""Add the persisted interface language preference.

Revision ID: d4a7c9012b3e
Revises: f42c91a7d011
Create Date: 2026-09-22
"""

import sqlalchemy as sa
from alembic import op


revision = 'd4a7c9012b3e'
down_revision = 'f42c91a7d011'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'user_preferences',
        sa.Column('language', sa.String(length=5), nullable=False, server_default='en'),
    )


def downgrade():
    op.drop_column('user_preferences', 'language')
