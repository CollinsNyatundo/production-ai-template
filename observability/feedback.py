import logging

logger = logging.getLogger("app.observability.feedback")

class FeedbackTracker:
    def __init__(self):
        # Local mock storage linking session or trace to feedback ratings
        self._feedback_logs = []

    async def log_user_feedback(self, session_id: str, rating: str, comment: str = "") -> None:
        # Rating could be "thumbs_up" or "thumbs_down"
        logger.info(f"Logging user feedback rating '{rating}' for session '{session_id}'")
        
        # In production, this pushes feedback payloads to trace tools (e.g. Langfuse score APIs)
        # to connect feedback scores directly to individual model trace runs.
        self._feedback_logs.append({
            "session_id": session_id,
            "rating": rating,
            "comment": comment
        })
        
        logger.info("Feedback linked successfully.")

feedback_tracker = FeedbackTracker()
