from typing import Dict, List

from app.services.deep_research.global_context import Fact


class SemanticDocumentAuditor:
    """Adversarial Agent 3: Strips marketing hype, checks context alignment, and rates source authority."""

    AUTHORITY_SCORES: Dict[str, float] = {
        "openkb": 1.0,
        "spec": 1.0,
        "code": 0.95,
        "benchmark": 0.85,
        "web": 0.60,
        "blog": 0.40,
        "unverified": 0.20,
    }

    HYPE_WORDS: List[str] = [
        "seamless",
        "revolutionary",
        "game-changing",
        "blazing fast",
        "industry-leading",
        "unmatched",
        "magic",
        "flawless",
        "zero effort",
    ]

    def audit_fact(self, content: str, source_name: str) -> Fact:
        """Strips hype words and assigns authority score based on source type."""
        clean_content = content
        for hw in self.HYPE_WORDS:
            clean_content = clean_content.replace(hw, "").replace(hw.capitalize(), "")

        clean_content = " ".join(clean_content.split())

        # Determine authority confidence score
        source_lower = source_name.lower()
        confidence = 0.5
        for key, score in self.AUTHORITY_SCORES.items():
            if key in source_lower:
                confidence = score
                break

        category = "general"
        if any(term in clean_content.lower() for term in ["error", "risk", "failure", "limit", "cost", "slow"]):
            category = "risk"
        elif any(term in clean_content.lower() for term in ["architecture", "code", "schema", "api", "function"]):
            category = "technical"
        elif any(term in clean_content.lower() for term in ["benchmark", "ms", "throughput", "percent", "%"]):
            category = "empirical"

        return Fact(
            content=clean_content,
            source=source_name,
            confidence=confidence,
            category=category,
        )
