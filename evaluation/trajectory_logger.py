import json
import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger("evaluation.trajectory_logger")


class TrajectoryLogger:
    def __init__(self, log_dir: str = "evaluation/eval_results"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "trajectory_runs.jsonl")

    async def log_run(
        self, session_id: str, query: str, trajectory: List[Dict[str, Any]], answer: str
    ) -> None:
        logger.info(f"Logging canonical evaluation trajectory to {self.log_file}")

        # Define canonical schema (V - Pitfall Mitigation)
        run_record = {
            "session_id": session_id,
            "query": query,
            "trajectory": trajectory,
            "final_answer": answer,
        }

        # Write to JSONL
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(run_record) + "\n")
            logger.info("Trajectory log successfully written.")
        except Exception as e:
            logger.error(f"Failed to write evaluation trajectory log: {e}")


trajectory_logger = TrajectoryLogger()
