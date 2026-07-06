import logging
from typing import Dict

logger = logging.getLogger("app.observability.cost_tracker")


class CostTracker:
    # Model prices per 1M tokens (as of typical mid-2026 pricing)
    PRICING_TABLE = {
        "gpt-4o": {"input": 5.00, "output": 15.00},
        "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    }

    async def track_usage(
        self, model: str, prompt_tokens: int, completion_tokens: int
    ) -> Dict[str, float]:
        logger.info(f"Tracking token usage for model '{model}'")

        # Calculate cost
        pricing = self.PRICING_TABLE.get(model, {"input": 0.0, "output": 0.0})

        input_cost = (prompt_tokens / 1_000_000.0) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000.0) * pricing["output"]
        total_cost = input_cost + output_cost

        logger.info(
            f"Usage calculated: {prompt_tokens} input, {completion_tokens} output. Total Cost: ${total_cost:.6f}"
        )

        return {
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": total_cost,
        }


cost_tracker = CostTracker()
