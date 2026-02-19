"""add board_task_pipelines

Revision ID: c4e7f2a1b8d3
Revises: b7a1d9c3e4f5
Create Date: 2026-02-19 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e7f2a1b8d3"
down_revision: str = "b7a1d9c3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "board_task_pipelines" in inspector.get_table_names():
        return

    op.create_table(
        "board_task_pipelines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_board_id", sa.Uuid(), nullable=False),
        sa.Column("target_board_id", sa.Uuid(), nullable=False),
        sa.Column("trigger_status", sa.String(), nullable=False, server_default="done"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("task_title_template", sa.String(), nullable=False, server_default=""),
        sa.Column("task_description_template", sa.Text(), nullable=True),
        sa.Column("target_agent_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["source_board_id"], ["boards.id"], name="fk_board_task_pipelines_source_board"),
        sa.ForeignKeyConstraint(["target_board_id"], ["boards.id"], name="fk_board_task_pipelines_target_board"),
        sa.ForeignKeyConstraint(["target_agent_id"], ["agents.id"], name="fk_board_task_pipelines_target_agent"),
    )
    op.create_index("ix_board_task_pipelines_source_board_id", "board_task_pipelines", ["source_board_id"])
    op.create_index("ix_board_task_pipelines_target_board_id", "board_task_pipelines", ["target_board_id"])
    op.create_index("ix_board_task_pipelines_target_agent_id", "board_task_pipelines", ["target_agent_id"])
    op.create_index("ix_board_task_pipelines_trigger_status", "board_task_pipelines", ["trigger_status"])
    op.create_index("ix_board_task_pipelines_enabled", "board_task_pipelines", ["enabled"])
    op.create_index(
        "ix_board_task_pipelines_source_trigger_enabled",
        "board_task_pipelines",
        ["source_board_id", "trigger_status", "enabled"],
    )


def downgrade() -> None:
    op.drop_index("ix_board_task_pipelines_source_trigger_enabled", table_name="board_task_pipelines")
    op.drop_index("ix_board_task_pipelines_enabled", table_name="board_task_pipelines")
    op.drop_index("ix_board_task_pipelines_trigger_status", table_name="board_task_pipelines")
    op.drop_index("ix_board_task_pipelines_target_agent_id", table_name="board_task_pipelines")
    op.drop_index("ix_board_task_pipelines_target_board_id", table_name="board_task_pipelines")
    op.drop_index("ix_board_task_pipelines_source_board_id", table_name="board_task_pipelines")
    op.drop_table("board_task_pipelines")
