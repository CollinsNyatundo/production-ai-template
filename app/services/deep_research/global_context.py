import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class Fact:
    """Represents a single extracted fact with source provenance and confidence score."""

    content: str
    source: str
    confidence: float = 0.9
    category: str = "general"  # technical, empirical, comparative, risk
    added_at_turn: int = 1
    fact_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class GlobalResearchContext:
    """Centralized state store for the Deep Research pipeline (prevents siloed knowledge)."""

    original_query: str
    topic_tree: List[Dict[str, Any]] = field(default_factory=list)
    facts: List[Fact] = field(default_factory=list)
    knowledge_gaps: List[str] = field(default_factory=list)
    kci_score: float = 0.0  # Knowledge Completeness Index (0.0 to 1.0)
    trajectory: List[Dict[str, Any]] = field(default_factory=list)
    adversarial_findings: List[Dict[str, Any]] = field(default_factory=list)

    def add_facts(self, new_facts: List[Fact]) -> int:
        """Adds new facts while filtering out exact or high semantic duplicates."""
        added_count = 0
        existing_contents_lower = {f.content.strip().lower() for f in self.facts}

        for f in new_facts:
            clean_content = f.content.strip().lower()
            if clean_content and clean_content not in existing_contents_lower:
                self.facts.append(f)
                existing_contents_lower.add(clean_content)
                added_count += 1

        return added_count

    def update_kci(self, new_score: float) -> None:
        """Updates the Knowledge Completeness Index."""
        self.kci_score = min(1.0, max(0.0, new_score))

    def get_summary_text(self) -> str:
        """Returns a condensed text representation of current research state for prompts."""
        facts_summary = "\n".join([f"- [{f.category.upper()}] {f.content} (Source: {f.source})" for f in self.facts])
        gaps_summary = "\n".join([f"- {g}" for g in self.knowledge_gaps])

        return (
            f"Original Query: {self.original_query}\n"
            f"Current KCI Score: {self.kci_score:.2f}/1.00\n"
            f"Verified Facts ({len(self.facts)} total):\n{facts_summary or 'None yet.'}\n\n"
            f"Current Knowledge Gaps:\n{gaps_summary or 'None identified yet.'}"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the research context to a dict."""
        return {
            "original_query": self.original_query,
            "topic_tree": self.topic_tree,
            "facts": [asdict(f) for f in self.facts],
            "knowledge_gaps": self.knowledge_gaps,
            "kci_score": self.kci_score,
            "trajectory": self.trajectory,
            "adversarial_findings": self.adversarial_findings,
        }
