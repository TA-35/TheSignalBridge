"""create pairing_codes table

A short-lived, single-use permission to register a passkey on a second
device. Only the hash is stored - see app/models/account.py.

Revision ID: c93e60f12a47
Revises: b2c7a1d4e905
Create Date: 2026-10-04 11:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c93e60f12a47'
down_revision = 'b2c7a1d4e905'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pairing_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code_hash'),
    )
    op.create_index(op.f('ix_pairing_codes_user_id'), 'pairing_codes', ['user_id'], unique=False)
    op.create_index(op.f('ix_pairing_codes_code_hash'), 'pairing_codes', ['code_hash'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_pairing_codes_code_hash'), table_name='pairing_codes')
    op.drop_index(op.f('ix_pairing_codes_user_id'), table_name='pairing_codes')
    op.drop_table('pairing_codes')
