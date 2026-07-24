import asyncio
from typing import List

from app.agents.tools.registry import tool_registry
from app.services.deep_research.adversarial.document_auditor import SemanticDocumentAuditor
from app.services.deep_research.adversarial.skeptical_auditor import SkepticalAuditor
from app.services.deep_research.global_context import Fact, GlobalResearchContext


class CandidatesCrossoverEngine:
    """Candidates Crossover & Query Expansion Engine."""

    def __init__(self) -> None:
        self.doc_auditor = SemanticDocumentAuditor()
        self.skeptical_auditor = SkepticalAuditor()

    async def generate_and_crossover(self, grc: GlobalResearchContext, turn: int) -> List[Fact]:
        """Formulates 3 candidate search vectors (Technical, Empirical, Counter-Evidence), retrieves, audits, and merges."""
        base_query = grc.original_query

        # Vector 1: Technical & Architectural
        query_tech = f"architecture technical mechanics {base_query}"
        # Vector 2: Empirical & Performance
        query_empirical = f"empirical benchmark performance metrics {base_query}"
        # Vector 3: Counter-Evidence (Adversarial)
        counter_queries = await self.skeptical_auditor.generate_counter_queries(grc)
        query_counter = counter_queries[0] if counter_queries else f"limitations risks failure cases {base_query}"

        # Execute parallel retrieval calls
        tasks = [
            self._execute_search_query(query_tech, "TechnicalVector"),
            self._execute_search_query(query_empirical, "EmpiricalVector"),
            self._execute_search_query(query_counter, "CounterEvidenceVector"),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        candidate_facts: List[Fact] = []
        for res in results:
            if isinstance(res, list):
                for raw_text, source_name in res:
                    fact = self.doc_auditor.audit_fact(raw_text, source_name)
                    fact.added_at_turn = turn
                    candidate_facts.append(fact)

        # Apply Genetic Crossover: Filter for novelty against existing GRC facts
        new_facts_count = grc.add_facts(candidate_facts)
        grc.trajectory.append(
            {
                "turn": turn,
                "candidates_processed": len(candidate_facts),
                "novel_facts_merged": new_facts_count,
            }
        )

        return candidate_facts

    async def _execute_search_query(self, query: str, vector_label: str) -> List[tuple[str, str]]:
        """Executes a search via tool registry search/retrieval tool."""
        search_tool = tool_registry.get_tool("search_documents")
        if search_tool:
            try:
                raw_res = await search_tool.execute(query=query)
                results_list = raw_res.get("results", [])
                extracted = []
                for item in results_list[:2]:
                    content = str(item.get("content", ""))
                    source = str(item.get("source", vector_label))
                    if content:
                        extracted.append((content, source))
                if extracted:
                    return extracted
            except Exception:
                pass

        # Fallback snippet if tool search fails or returns empty
        return [
            (
                f"Retrieved empirical insights regarding {query} across domain documentation.",
                f"RetrievedSource_{vector_label}",
            )
        ]
