import logging
from typing import Any, Dict

from app.services.deep_research.adversarial import (
    CrossDomainStressTester,
    PremiseRedTeamer,
)
from app.services.deep_research.crossover import CandidatesCrossoverEngine
from app.services.deep_research.global_context import GlobalResearchContext
from app.services.deep_research.planner import ResearchPlanner
from app.services.deep_research.reflector import PlanReflector
from app.services.deep_research.synthesizer import OneShotReportSynthesizer

logger = logging.getLogger("app.services.deep_research.orchestrator")


class DeepResearchOrchestrator:
    """Master Orchestrator for the Deep Research Pipeline with 5 Adversarial Agents."""

    def __init__(self, max_depth: int = 3) -> None:
        self.max_depth = max_depth
        self.planner = ResearchPlanner()
        self.reflector = PlanReflector()
        self.crossover_engine = CandidatesCrossoverEngine()
        self.synthesizer = OneShotReportSynthesizer()
        self.premise_red_teamer = PremiseRedTeamer()
        self.stress_tester = CrossDomainStressTester()

    async def execute(self, query: str, session_id: str) -> Dict[str, Any]:
        """Executes the full Deep Research loop."""
        logger.info(f"Starting Deep Research for session '{session_id}': '{query}'")
        grc = GlobalResearchContext(original_query=query)

        # Step 1: Premise Red-Teaming (Adversarial Agent 1)
        premise_attack = await self.premise_red_teamer.analyze_premises(query)
        grc.adversarial_findings.append(premise_attack)

        # Step 2: Hierarchical Task Graph Planning
        await self.planner.create_plan(grc)

        # Step 3: Sequential Reflection & Candidates Crossover Loop
        for turn in range(1, self.max_depth + 1):
            logger.info(f"Deep Research Turn {turn}/{self.max_depth} for session '{session_id}'")

            reflection = await self.reflector.reflect(grc, current_turn=turn, max_turns=self.max_depth)

            if reflection.should_stop:
                logger.info(f"Deep Research reflection threshold met on turn {turn}.")
                break

            await self.crossover_engine.generate_and_crossover(grc, turn=turn)

        # Step 4: Cross-Domain Stress-Testing (Adversarial Agent 4)
        stress_facts = await self.stress_tester.generate_stress_test_facts(grc)
        grc.add_facts(stress_facts)

        # Step 5: One-Shot Fact-Dense Report Synthesis with Synthesis Referee
        report = await self.synthesizer.generate_report(grc)

        return {
            "query": query,
            "session_id": session_id,
            "answer": report,
            "sources": [
                {
                    "content": f.content,
                    "metadata": {"source": f.source, "confidence": f.confidence, "category": f.category},
                }
                for f in grc.facts
            ],
            "trajectory": grc.trajectory,
            "kci_score": grc.kci_score,
            "adversarial_findings": grc.adversarial_findings,
        }
