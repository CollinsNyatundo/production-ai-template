from typing import List, Tuple

from app.services.deep_research.global_context import Fact, GlobalResearchContext


class SynthesisReferee:
    """Adversarial Agent 5: Arbitrates conflicting evidence and structures the final Risk & Counter-Evidence Matrix."""

    def arbitrate_and_structure(self, grc: GlobalResearchContext) -> Tuple[List[Fact], List[Fact]]:
        """Separates verified core findings from risk/counter-evidence facts for balanced report rendering."""
        core_facts: List[Fact] = []
        risk_facts: List[Fact] = []

        for fact in grc.facts:
            if fact.category == "risk" or fact.confidence < 0.6:
                risk_facts.append(fact)
            else:
                core_facts.append(fact)

        return core_facts, risk_facts

    def generate_risk_matrix_markdown(self, risk_facts: List[Fact]) -> str:
        """Generates a structured markdown risk & counter-evidence section."""
        if not risk_facts:
            return "### ⚠️ Risk & Counter-Evidence Analysis\n- No major operational or technical risks flagged.\n"

        rows = []
        for rf in risk_facts:
            rows.append(f"| `{rf.category.upper()}` | {rf.content} | `{rf.confidence:.2f}` | {rf.source} |")

        table_header = (
            "### ⚠️ Risk, Counter-Evidence & Trade-Off Matrix\n\n"
            "| Category | Counter-Fact / Failure Risk | Confidence | Source Authority |\n"
            "| :--- | :--- | :--- | :--- |\n"
        )
        return table_header + "\n".join(rows) + "\n"
