from typing import Any, Dict

from app.services.llm_client import llm_client


class PremiseRedTeamer:
    """Adversarial Agent 1: Attacks load-bearing assumptions in the research query."""

    async def analyze_premises(self, query: str) -> Dict[str, Any]:
        """Analyzes query for implicit assumptions and categorizes into Tigers, Paper Tigers, and Elephants."""
        prompt = (
            f"You are a fierce Adversarial Red-Team Research Agent.\n"
            f"Analyze the following research query for load-bearing implicit assumptions:\n"
            f'QUERY: "{query}"\n\n'
            f"Identify 3 distinct categories of risks/premises:\n"
            f"1. TIGERS: Real, high-impact failure risks or flaws in the user's implicit premise.\n"
            f"2. PAPER TIGERS: Overblown concerns that look scary but are actually non-issues.\n"
            f"3. ELEPHANTS: Unspoken, uncomfortable truths (costs, tech debt, organizational friction).\n\n"
            f"Provide a brief bulleted breakdown for each category."
        )

        try:
            resp = await llm_client.chat(
                messages=[
                    {"role": "system", "content": "You are a critical, non-sycophantic adversarial red-team auditor."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=600,
            )
            analysis = resp.choices[0].message.content or "No premise attack generated."
        except Exception as err:
            analysis = f"Premise analysis fallback due to LLM offline status: {err}"

        return {
            "agent": "PremiseRedTeamer",
            "query": query,
            "analysis": analysis,
        }
