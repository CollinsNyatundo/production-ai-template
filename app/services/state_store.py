import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select

from app.services.database import (
    AgentCheckpoint,
    Base,
    ConversationMessage,
    async_session,
    engine,
)

logger = logging.getLogger("app.services.state_store")


class StateStore:
    def __init__(self):
        logger.info("Persistent State Store initialized utilizing SQLAlchemy ORM.")

    async def initialize_tables(self) -> None:
        """Initializes database schema tables synchronously within the async flow."""
        logger.info("Initializing persistent database schema tables...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Schema tables check complete.")

    async def save_message(self, session_id: str, role: str, content: str) -> None:
        logger.info(f"Saving message to state store for session '{session_id}'")
        async with async_session() as session:
            async with session.begin():
                msg = ConversationMessage(
                    session_id=session_id, role=role, content=content
                )
                session.add(msg)
            # Commit is handled automatically by the context manager begin block

    async def get_history(self, session_id: str) -> List[Dict[str, str]]:
        logger.info(f"Loading history from state store for session '{session_id}'")
        async with async_session() as session:
            stmt = (
                select(ConversationMessage)
                .where(ConversationMessage.session_id == session_id)
                .order_by(ConversationMessage.id.asc())
            )
            result = await session.execute(stmt)
            messages = result.scalars().all()
            return [{"role": msg.role, "content": msg.content} for msg in messages]

    async def clear_history(self, session_id: str) -> None:
        logger.info(f"Clearing history from state store for session '{session_id}'")
        async with async_session() as session:
            async with session.begin():
                stmt = delete(ConversationMessage).where(
                    ConversationMessage.session_id == session_id
                )
                await session.execute(stmt)

    async def save_checkpoint(
        self,
        session_id: str,
        current_step: int,
        state: Dict[str, Any],
        trajectory: List[Dict[str, Any]],
    ) -> None:
        logger.info(
            f"Saving agent checkpoint step {current_step} for session '{session_id}'"
        )
        async with async_session() as session:
            async with session.begin():
                # Select first to support database-agnostic update/insert
                stmt = select(AgentCheckpoint).where(
                    AgentCheckpoint.session_id == session_id
                )
                result = await session.execute(stmt)
                checkpoint = result.scalar_one_or_none()

                state_str = json.dumps(state)
                traj_str = json.dumps(trajectory)

                if checkpoint:
                    checkpoint.current_step = current_step
                    checkpoint.state_json = state_str
                    checkpoint.trajectory_json = traj_str
                else:
                    checkpoint = AgentCheckpoint(
                        session_id=session_id,
                        current_step=current_step,
                        state_json=state_str,
                        trajectory_json=traj_str,
                    )
                    session.add(checkpoint)

    async def load_checkpoint(self, session_id: str) -> Optional[Dict[str, Any]]:
        logger.info(f"Loading agent checkpoint snapshot for session '{session_id}'")
        async with async_session() as session:
            stmt = select(AgentCheckpoint).where(
                AgentCheckpoint.session_id == session_id
            )
            result = await session.execute(stmt)
            checkpoint = result.scalar_one_or_none()
            if not checkpoint:
                return None
            return {
                "current_step": checkpoint.current_step,
                "state": json.loads(checkpoint.state_json),
                "trajectory": json.loads(checkpoint.trajectory_json),
            }

    async def clear_checkpoint(self, session_id: str) -> None:
        logger.info(f"Clearing agent checkpoint snapshot for session '{session_id}'")
        async with async_session() as session:
            async with session.begin():
                stmt = delete(AgentCheckpoint).where(
                    AgentCheckpoint.session_id == session_id
                )
                await session.execute(stmt)


state_store = StateStore()
