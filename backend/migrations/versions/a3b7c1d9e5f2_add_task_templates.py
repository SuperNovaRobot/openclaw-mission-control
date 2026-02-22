"""add task_templates

Revision ID: a3b7c1d9e5f2
Revises: d5f8a3b2c9e1
Create Date: 2026-02-22 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3b7c1d9e5f2"
down_revision: str = "d5f8a3b2c9e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task_templates" in inspector.get_table_names():
        return

    op.create_table(
        "task_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("board_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("title_template", sa.String(), nullable=False, server_default=""),
        sa.Column("description_template", sa.Text(), nullable=True),
        sa.Column("created_from_task_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_task_templates_organization"),
        sa.ForeignKeyConstraint(["board_id"], ["boards.id"], name="fk_task_templates_board"),
    )
    op.create_index("ix_task_templates_organization_id", "task_templates", ["organization_id"])
    op.create_index("ix_task_templates_board_id", "task_templates", ["board_id"])


def downgrade() -> None:
    op.drop_index("ix_task_templates_board_id", table_name="task_templates")
    op.drop_index("ix_task_templates_organization_id", table_name="task_templates")
    op.drop_table("task_templates")
