import logging
from typing import Dict, List, Optional

from app.config import settings
from observability.tracer import current_user_context

logger = logging.getLogger("app.observability.feedback")


class FeedbackTracker:
    def __init__(self) -> None:
        # Local in-memory storage when AWS_BACKEND_ENABLED=false
        self._feedback_logs: List[Dict[str, str]] = []

    async def log_user_feedback(
        self,
        session_id: str,
        rating: str,
        comment: str = "",
        tenant_id: Optional[str] = None,
    ) -> Optional[str]:
        # Rating could be "thumbs_up" or "thumbs_down"
        logger.info(f"Logging user feedback rating '{rating}' for session '{session_id}'")
        ctx = current_user_context.get()
        effective_tenant = tenant_id or (ctx["tenant_id"] if ctx else "default-tenant")

        self._feedback_logs.append(
            {"tenant_id": effective_tenant, "session_id": session_id, "rating": rating, "comment": comment}
        )

        feedback_id: Optional[str] = None
        if settings.aws_backend_enabled:
            from app.cloud.queue_store import dynamodb_state_repo

            feedback_id = await dynamodb_state_repo.put_feedback(
                tenant_id=effective_tenant,
                session_id=session_id,
                rating=rating,
                comment=comment,
            )

        logger.info("Feedback linked successfully.")
        return feedback_id


feedback_tracker = FeedbackTracker()
