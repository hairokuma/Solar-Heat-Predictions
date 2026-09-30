"""add custom locations

Revision ID: c7d2e4f8a1b3
Revises: a3f1c9d2e7b4
Create Date: 2026-09-30 12:00:00.000000

"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7d2e4f8a1b3'
down_revision = 'a3f1c9d2e7b4'
branch_labels = None
depends_on = None

DEFAULT_LOCATIONS = ('home', 'conservatory')


def upgrade():
    custom_locations = op.create_table('custom_locations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )

    # Garden used to be built in: keep any location that already has readings
    # or sensors (in practice just "garden") as a custom one, so its data stays
    # visible and its sensors keep working.
    conn = op.get_bind()
    existing = conn.execute(sa.text(
        'SELECT location FROM temperature_readings UNION SELECT location FROM sensors'
    )).scalars()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = [{'name': name, 'created_at': now} for name in sorted(set(existing)) if name not in DEFAULT_LOCATIONS]
    if rows:
        op.bulk_insert(custom_locations, rows)


def downgrade():
    op.drop_table('custom_locations')
