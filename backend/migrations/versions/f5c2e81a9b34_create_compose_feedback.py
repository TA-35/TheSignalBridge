"""create compose_feedback table

A 👍/👎 on a Compose rewrite: the vote, reason codes from a fixed list, the
model's name and two yes/no facts about the flow. No text of any kind and no
account - see app/models/compose_feedback.py.

Revision ID: f5c2e81a9b34
Revises: e7a3c95d1f20
Create Date: 2026-10-12 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f5c2e81a9b34'
down_revision = 'e7a3c95d1f20'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'compose_feedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('vote', sa.String(length=4), nullable=False),
        sa.Column('reasons', sa.String(length=200), nullable=False),
        sa.Column('kept_as_written', sa.Boolean(), nullable=False),
        sa.Column('after_card', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_compose_feedback_model'), 'compose_feedback', ['model'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_compose_feedback_model'), table_name='compose_feedback')
    op.drop_table('compose_feedback')
