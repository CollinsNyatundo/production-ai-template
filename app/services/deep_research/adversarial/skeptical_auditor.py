from typing import List

from app.services.deep_research.global_context import GlobalResearchContext
from app.services.llm_client import llm_client


class SkepticalAuditor:
    """Adversarial Agent 2: Counter-fact finder that formulates adversarial queries to challenge gathered facts."""

    async def generate_counter_queries(self, grc: GlobalResearchContext) -> List[str]:
        """Generates counter-evidence queries based on current verified facts."""
        if not grc.facts:
            return [f"limitations failure modes drawbacks of {grc.original_query}"]

        recent_facts = "\n".join([f"- {f.content}" for f in grc.facts[-5:]])
        prompt = (
            f"You are a Skeptical Audit Agent.\n"
            f"Given these current research claims:\n{recent_facts}\n\n"
            f"Formulate 3 specific, targeted search queries to find CONTRADICATIONS, failure cases, "
            f"security risks, or performance bottlenecks regarding these claims.\n"
            f"Output exactly 3 search queries, one per line, with no extra text."
        )

        try:
            resp = await llm_client.chat(
                messages=[
                    {"role": "system", "content": "You generate counter-evidence search queries."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=250,
            )
            raw_lines = (resp.choices[0].message.content or "").strip().split("\n")
            queries = [q.strip("- 123456789. ") for q in raw_lines if q.strip()]
            return queries[:3]
        except Exception:
            return [f"known issues limitations drawbacks of {grc.original_query}"]
