"""Create users table

Revision ID: 000
Revises:
Create Date: 2025-01-28 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guard: this codebase also provisions schema via
    # Base.metadata.create_all() at startup, so skip when the target
    # already exists (fresh DBs get everything from create_all).
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("users"):
        return

    # Create users table first (required by other tables)
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("phone_number", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, default=True),
        sa.Column("is_verified", sa.Boolean(), nullable=True, default=False),
        sa.Column("is_admin", sa.Boolean(), nullable=True, default=False),
        sa.Column("zip_code", sa.String(), nullable=True),
        sa.Column("council_district", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    # Create user_interests table
    op.create_table(
        "user_interests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("interest", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_interests_id"), "user_interests", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_interests_id"), table_name="user_interests")
    op.drop_table("user_interests")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users") 