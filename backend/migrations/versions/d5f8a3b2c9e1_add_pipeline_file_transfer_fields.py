"""add pipeline file transfer and notification fields

Revision ID: d5f8a3b2c9e1
Revises: c4e7f2a1b8d3
Create Date: 2026-02-20 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5f8a3b2c9e1"
down_revision: str = "c4e7f2a1b8d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("board_task_pipelines")}

    if "transfer_files" not in columns:
        op.add_column(
            "board_task_pipelines",
            sa.Column("transfer_files", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    if "notify_agent" not in columns:
        op.add_column(
            "board_task_pipelines",
            sa.Column("notify_agent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    if "notification_template" not in columns:
        op.add_column(
            "board_task_pipelines",
            sa.Column("notification_template", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("board_task_pipelines", "notification_template")
    op.drop_column("board_task_pipelines", "notify_agent")
    op.drop_column("board_task_pipelines", "transfer_files")
