"""initial_schema

Revision ID: bd4839f96b99
Revises:
Create Date: 2026-07-07 01:43:04.245649

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bd4839f96b99"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Create conversation_history and agent_checkpoints tables."""
    # 1. Create conversation_history table
    op.create_table(
        "conversation_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    # Add performance index on session_id for query speed
    op.create_index("ix_conversation_history_session_id", "conversation_history", ["session_id"], unique=False)

    # 2. Create agent_checkpoints table
    op.create_table(
        "agent_checkpoints",
        sa.Column("session_id", sa.String(length=255), primary_key=True),
        sa.Column("current_step", sa.Integer(), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("trajectory_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Downgrade schema: Drop conversation_history and agent_checkpoints tables."""
    op.drop_table("agent_checkpoints")
    op.drop_index("ix_conversation_history_session_id", table_name="conversation_history")
    op.drop_table("conversation_history")
