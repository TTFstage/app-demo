"""Harden ownership cascades and worker idempotency.

Revision ID: c51a9f0e42d1
Revises: 1376cf71df75
Create Date: 2026-09-17
"""

from alembic import op

revision = 'c51a9f0e42d1'
down_revision = '1376cf71df75'
branch_labels = None
depends_on = None


def upgrade():
    # Keep the newest row if older deployments already contain duplicates.
    op.execute(
        """
        DELETE FROM rider_shifts older
        USING rider_shifts newer
        WHERE older.user_id = newer.user_id
          AND older.session_id = newer.session_id
          AND older.id < newer.id
        """
    )
    op.execute(
        """
        DELETE FROM fall_events older
        USING fall_events newer
        WHERE older.user_id = newer.user_id
          AND older.session_id = newer.session_id
          AND older.timestamp = newer.timestamp
          AND older.id < newer.id
        """
    )

    op.create_unique_constraint(
        'uq_rider_shifts_user_session', 'rider_shifts', ['user_id', 'session_id']
    )
    op.create_unique_constraint(
        'uq_fall_events_user_session_timestamp',
        'fall_events',
        ['user_id', 'session_id', 'timestamp'],
    )

    for table in ('rider_shifts', 'fall_events', 'activities'):
        op.drop_constraint(f'{table}_user_id_fkey', table, type_='foreignkey')
        op.create_foreign_key(
            f'{table}_user_id_fkey', table, 'user', ['user_id'], ['id'], ondelete='CASCADE'
        )


def downgrade():
    for table in ('rider_shifts', 'fall_events', 'activities'):
        op.drop_constraint(f'{table}_user_id_fkey', table, type_='foreignkey')
        op.create_foreign_key(
            f'{table}_user_id_fkey', table, 'user', ['user_id'], ['id']
        )

    op.drop_constraint(
        'uq_fall_events_user_session_timestamp', 'fall_events', type_='unique'
    )
    op.drop_constraint('uq_rider_shifts_user_session', 'rider_shifts', type_='unique')
