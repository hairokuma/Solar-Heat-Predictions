"""add reading humidity

Revision ID: a3f1c9d2e7b4
Revises: 54b4e5c0d0bc
Create Date: 2026-09-30 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3f1c9d2e7b4'
down_revision = '54b4e5c0d0bc'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('temperature_readings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('humidity_pct', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('temperature_readings', schema=None) as batch_op:
        batch_op.drop_column('humidity_pct')
