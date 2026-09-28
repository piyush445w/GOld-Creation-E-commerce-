"""increase_country_field_length

Revision ID: 29ce823c2cca
Revises: a1b2c3d4e5f6
Create Date: 2026-09-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '29ce823c2cca'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('addresses', 'country',
               existing_type=mysql.VARCHAR(length=2),
               type_=sa.String(length=100),
               existing_nullable=False)
    op.alter_column('users', 'country',
               existing_type=mysql.VARCHAR(length=2),
               type_=sa.String(length=100),
               existing_nullable=True)


def downgrade():
    op.alter_column('users', 'country',
               existing_type=sa.String(length=100),
               type_=mysql.VARCHAR(length=2),
               existing_nullable=True)
    op.alter_column('addresses', 'country',
               existing_type=sa.String(length=100),
               type_=mysql.VARCHAR(length=2),
               existing_nullable=False)
