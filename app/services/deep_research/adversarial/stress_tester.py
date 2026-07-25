from typing import List

from app.services.deep_research.global_context import Fact, GlobalResearchContext
from app.services.llm_client import llm_client


class CrossDomainStressTester:
    """Adversarial Agent 4: Injects edge cases, failure modes, security, and compliance stress tests."""

    async def generate_stress_test_facts(self, grc: GlobalResearchContext) -> List[Fact]:
        """Generates cross-domain stress test scenarios for current topic."""
        prompt = (
            f"You are a Cross-Domain Reliability & Edge-Case Stress-Tester Agent.\n"
            f'Given the topic: "{grc.original_query}"\n\n'
            f"Identify 2 severe edge-case risks, failure modes, or compliance constraints "
            f"(e.g., concurrency races, security/PCI-DSS vulnerabilities, cost spikes, or scale limits).\n"
            f"Output exactly 2 clear factual warnings, one per line."
        )

        try:
            resp = await llm_client.chat(
                messages=[
                    {"role": "system", "content": "You are a software & system stress-testing auditor."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=300,
            )
            raw_text = resp.choices[0].message.content or ""
            lines = [line.strip("- 123456789. ") for line in raw_text.split("\n") if line.strip()]

            return [
                Fact(
                    content=line,
                    source="CrossDomainStressTester",
                    confidence=0.9,
                    category="risk",
                )
                for line in lines[:2]
            ]
        except Exception:
            return [
                Fact(
                    content=f"Under high load or unexpected inputs, {grc.original_query} may experience latency degradation or concurrency lock contention.",
                    source="CrossDomainStressTester",
                    confidence=0.8,
                    category="risk",
                )
            ]
