"""create user_activity and user_phrase_events tables

Progress-dashboard data an account carries between devices: minutes per
feature per day (per device), days the app was opened, and which library
patterns were viewed or reviewed on which day. Dates, counts and pattern ids
only - the focus timer's free-text intent stays in the browser. See
app/models/user_progress.py.

Revision ID: e7a3c95d1f20
Revises: d41b8c20f7e3
Create Date: 2026-10-10 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7a3c95d1f20'
down_revision = 'd41b8c20f7e3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_activity',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('device_id', sa.String(length=36), nullable=False),
        sa.Column('date', sa.String(length=10), nullable=False),
        sa.Column('feature', sa.String(length=16), nullable=False),
        sa.Column('minutes', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id', 'device_id', 'date', 'feature',
            name='uq_user_activity_user_device_day_feature',
        ),
    )
    op.create_index(op.f('ix_user_activity_user_id'), 'user_activity', ['user_id'], unique=False)

    op.create_table(
        'user_phrase_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('pattern_id', sa.String(length=40), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('date', sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id', 'pattern_id', 'kind', 'date',
            name='uq_user_phrase_events_user_pattern_kind_day',
        ),
    )
    op.create_index(op.f('ix_user_phrase_events_user_id'), 'user_phrase_events', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_user_phrase_events_user_id'), table_name='user_phrase_events')
    op.drop_table('user_phrase_events')
    op.drop_index(op.f('ix_user_activity_user_id'), table_name='user_activity')
    op.drop_table('user_activity')
