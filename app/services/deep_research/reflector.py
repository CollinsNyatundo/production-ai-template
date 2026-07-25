from dataclasses import dataclass
from typing import List

from app.services.deep_research.global_context import GlobalResearchContext
from app.services.llm_client import llm_client


@dataclass
class ReflectionResult:
    kci_score: float
    should_stop: bool
    reflection_note: str
    remaining_gaps: List[str]


class PlanReflector:
    """Sequential Plan Reflector & Knowledge Completeness Index (KCI) Evaluator."""

    async def reflect(self, grc: GlobalResearchContext, current_turn: int, max_turns: int = 4) -> ReflectionResult:
        """Evaluates current research progress, updates KCI score, and decides whether to continue."""
        num_facts = len(grc.facts)
        categories = {f.category for f in grc.facts}

        # Calculate heuristic base KCI
        base_kci = min(1.0, (num_facts * 0.15) + (len(categories) * 0.10))
        grc.update_kci(base_kci)

        if current_turn >= max_turns or grc.kci_score >= 0.85:
            return ReflectionResult(
                kci_score=grc.kci_score,
                should_stop=True,
                reflection_note=f"Target Knowledge Completeness Index achieved ({grc.kci_score:.2f}) or turn cap reached ({current_turn}/{max_turns}).",
                remaining_gaps=grc.knowledge_gaps,
            )

        prompt = (
            f"You are a Sequential Plan Reflector.\n"
            f"Review current research state:\n{grc.get_summary_text()}\n\n"
            f"State what critical information is still missing in 1 concise sentence."
        )

        try:
            resp = await llm_client.chat(
                messages=[
                    {"role": "system", "content": "You evaluate research progress and gaps."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=150,
            )
            note = resp.choices[0].message.content or "Continuing research to fill remaining gaps."
        except Exception:
            note = "Continuing research to gather empirical evidence and risk factors."

        return ReflectionResult(
            kci_score=grc.kci_score,
            should_stop=False,
            reflection_note=note,
            remaining_gaps=grc.knowledge_gaps,
        )
