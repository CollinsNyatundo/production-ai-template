from typing import Any, Dict

from app.services.deep_research.global_context import GlobalResearchContext
from app.services.llm_client import llm_client


class ResearchPlanner:
    """Hierarchical Task Graph Planner for Deep Research."""

    async def create_plan(self, grc: GlobalResearchContext) -> Dict[str, Any]:
        """Formulates a 4-phase research graph and initial knowledge gaps."""
        prompt = (
            f"You are a Senior Principal Research Architect.\n"
            f"Formulate a structured 4-phase research breakdown for:\n"
            f'TARGET TOPIC: "{grc.original_query}"\n\n'
            f"The 4 phases are:\n"
            f"Phase 1: Foundational Landscape & Concepts\n"
            f"Phase 2: Technical Architecture & Core Mechanics\n"
            f"Phase 3: Empirical Performance & Comparative Analysis\n"
            f"Phase 4: Operational Risks, Edge Cases & Failure Modes\n\n"
            f"Provide 4 concise research sub-questions, one for each phase, on separate lines."
        )

        try:
            resp = await llm_client.chat(
                messages=[
                    {"role": "system", "content": "You create structured research task graphs."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=350,
            )
            raw_text = resp.choices[0].message.content or ""
            sub_questions = [line.strip("- 123456789. ") for line in raw_text.split("\n") if line.strip()]
        except Exception:
            sub_questions = [
                f"Foundational concepts of {grc.original_query}",
                f"Technical architecture and mechanics of {grc.original_query}",
                f"Empirical benchmarks and comparisons for {grc.original_query}",
                f"Known risks and edge cases of {grc.original_query}",
            ]

        grc.knowledge_gaps = sub_questions[:4]
        grc.topic_tree = [
            {"phase": idx + 1, "topic": q, "status": "PENDING"} for idx, q in enumerate(grc.knowledge_gaps)
        ]

        return {
            "query": grc.original_query,
            "phases": grc.topic_tree,
            "initial_gaps": grc.knowledge_gaps,
        }
