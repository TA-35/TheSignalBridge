"""create users and credentials tables

Accounts held by a passkey: a user is a handle and a pair of timestamps, and
a credential is one registered authenticator's public key. No email, no
password hash, no message text - see app/models/account.py.

Revision ID: b2c7a1d4e905
Revises: 1ef8f51eebea
Create Date: 2026-10-03 21:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c7a1d4e905'
down_revision = '1ef8f51eebea'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('handle', sa.String(length=8), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('handle'),
    )
    op.create_index(op.f('ix_users_handle'), 'users', ['handle'], unique=True)

    op.create_table(
        'credentials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('credential_id', sa.LargeBinary(), nullable=False),
        sa.Column('public_key', sa.LargeBinary(), nullable=False),
        sa.Column('sign_count', sa.Integer(), nullable=False),
        sa.Column('transports', sa.String(length=120), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        # Deleting an account takes its passkeys with it, in the database
        # rather than in application code - "delete my account" must not
        # depend on the app remembering to tidy up.
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('credential_id'),
    )
    op.create_index(op.f('ix_credentials_user_id'), 'credentials', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_credentials_user_id'), table_name='credentials')
    op.drop_table('credentials')
    op.drop_index(op.f('ix_users_handle'), table_name='users')
    op.drop_table('users')
