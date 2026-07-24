import pytest

from app.services.deep_research.adversarial import (
    SemanticDocumentAuditor,
    SynthesisReferee,
)
from app.services.deep_research.global_context import Fact, GlobalResearchContext
from app.services.deep_research.orchestrator import DeepResearchOrchestrator
from app.services.deep_research.planner import ResearchPlanner
from app.services.deep_research.reflector import PlanReflector


@pytest.mark.asyncio
async def test_global_context_fact_deduplication():
    grc = GlobalResearchContext(original_query="Test query")
    f1 = Fact(content="PostgreSQL handles JSONB efficiently.", source="DocA")
    f2 = Fact(content="postgresql handles jsonb efficiently.", source="DocB")  # Duplicate
    f3 = Fact(content="PostgreSQL supports multi-version concurrency control.", source="DocC")

    added = grc.add_facts([f1, f2, f3])
    assert added == 2
    assert len(grc.facts) == 2


@pytest.mark.asyncio
async def test_planner_graph_formulation():
    planner = ResearchPlanner()
    grc = GlobalResearchContext(original_query="Microservices vs Monolith")
    plan_dict = await planner.create_plan(grc)

    assert "phases" in plan_dict
    assert len(grc.knowledge_gaps) == 4
    assert len(grc.topic_tree) == 4


@pytest.mark.asyncio
async def test_reflector_kci_scoring():
    reflector = PlanReflector()
    grc = GlobalResearchContext(original_query="Kafka throughput limits")
    grc.add_facts(
        [
            Fact(content="Fact 1", source="A", category="technical"),
            Fact(content="Fact 2", source="B", category="empirical"),
            Fact(content="Fact 3", source="C", category="risk"),
        ]
    )

    res = await reflector.reflect(grc, current_turn=1, max_turns=3)
    assert res.kci_score > 0.0
    assert isinstance(res.should_stop, bool)


@pytest.mark.asyncio
async def test_semantic_document_auditor_hype_stripping():
    auditor = SemanticDocumentAuditor()
    raw = "Our revolutionary and blazing fast database is industry-leading."
    fact = auditor.audit_fact(raw, "OpenKB Spec")

    assert "revolutionary" not in fact.content
    assert "blazing fast" not in fact.content
    assert fact.confidence == 1.0


@pytest.mark.asyncio
async def test_synthesis_referee_risk_matrix():
    referee = SynthesisReferee()
    grc = GlobalResearchContext(original_query="TLS handshake performance")
    grc.add_facts(
        [
            Fact(content="TLS 1.3 cuts handshake RTT in half.", source="RFC 8446", category="technical"),
            Fact(content="RSA key exchange suffers CPU overhead under 10k QPS.", source="Benchmark", category="risk"),
        ]
    )

    core, risks = referee.arbitrate_and_structure(grc)
    assert len(core) == 1
    assert len(risks) == 1

    matrix_md = referee.generate_risk_matrix_markdown(risks)
    assert "Risk, Counter-Evidence & Trade-Off Matrix" in matrix_md


@pytest.mark.asyncio
async def test_deep_research_orchestrator_execution():
    orchestrator = DeepResearchOrchestrator(max_depth=1)
    res = await orchestrator.execute("OAuth2 Token Security", session_id="test-session-123")

    assert "answer" in res
    assert "sources" in res
    assert "adversarial_findings" in res
    assert len(res["adversarial_findings"]) > 0
