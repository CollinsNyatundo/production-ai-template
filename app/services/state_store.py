import sqlite3
import json
import logging
import os
from typing import List, Dict, Any, Optional

logger = logging.getLogger("app.services.state_store")

class StateStore:
    def __init__(self, db_path: str = "app.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        logger.info(f"Initializing persistent SQLite State Store at: {os.path.abspath(self.db_path)}")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Conversation memory table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Agent checkpoint state table (E/S - Pitfall Mitigation)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_checkpoints (
                    session_id TEXT PRIMARY KEY,
                    current_step INTEGER,
                    state_json TEXT,
                    trajectory_json TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    async def save_message(self, session_id: str, role: str, content: str) -> None:
        logger.info(f"Saving message to state store for session '{session_id}'")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO conversation_history (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content)
            )
            conn.commit()

    async def get_history(self, session_id: str) -> List[Dict[str, str]]:
        logger.info(f"Loading history from state store for session '{session_id}'")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT role, content FROM conversation_history WHERE session_id = ? ORDER BY id ASC",
                (session_id,)
            )
            rows = cursor.fetchall()
            return [{"role": r[0], "content": r[1]} for r in rows]

    async def clear_history(self, session_id: str) -> None:
        logger.info(f"Clearing history from state store for session '{session_id}'")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM conversation_history WHERE session_id = ?", (session_id,))
            conn.commit()

    # Agent Checkpointing snapshot logic (S - Gap Mitigation)
    async def save_checkpoint(self, session_id: str, current_step: int, state: Dict[str, Any], trajectory: List[Dict[str, Any]]) -> None:
        logger.info(f"Saving agent checkpoint step {current_step} for session '{session_id}'")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agent_checkpoints (session_id, current_step, state_json, trajectory_json, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    current_step = excluded.current_step,
                    state_json = excluded.state_json,
                    trajectory_json = excluded.trajectory_json,
                    updated_at = CURRENT_TIMESTAMP
            """, (session_id, current_step, json.dumps(state), json.dumps(trajectory)))
            conn.commit()

    async def load_checkpoint(self, session_id: str) -> Optional[Dict[str, Any]]:
        logger.info(f"Loading agent checkpoint snapshot for session '{session_id}'")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT current_step, state_json, trajectory_json FROM agent_checkpoints WHERE session_id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "current_step": row[0],
                "state": json.loads(row[1]),
                "trajectory": json.loads(row[2])
            }

state_store = StateStore()
