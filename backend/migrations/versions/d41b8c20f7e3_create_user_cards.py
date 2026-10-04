"""create user_cards table

Library cards an account carries between devices: which curated pattern,
when it was kept, when it was last opened. No message text - cards saved
from a decode stay in the browser. See app/models/user_card.py.

Revision ID: d41b8c20f7e3
Revises: c93e60f12a47
Create Date: 2026-10-05 10:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd41b8c20f7e3'
down_revision = 'c93e60f12a47'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_cards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('pattern_id', sa.String(length=40), nullable=False),
        sa.Column('saved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_opened_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'pattern_id', name='uq_user_cards_user_pattern'),
    )
    op.create_index(op.f('ix_user_cards_user_id'), 'user_cards', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_user_cards_user_id'), table_name='user_cards')
    op.drop_table('user_cards')
