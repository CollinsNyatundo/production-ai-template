import asyncio
import json
import logging
import os
import sys

# Ensure python path is set correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models import QueryRequest
from app.security.auth import User
from app.services.rag_pipeline import rag_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("evaluation.offline_eval")


async def run_evaluation() -> int:
    logger.info("Starting offline RAG evaluation run...")

    # 1. Load dataset schema
    dataset_path = os.path.join(os.path.dirname(__file__), "golden_dataset.json")
    with open(dataset_path, "r") as f:
        test_cases = json.load(f)

    logger.info(f"Loaded {len(test_cases)} evaluation cases.")

    results = []
    failed_cases = []

    # Create an authenticated mock admin user context for pipeline run
    mock_user = User(
        username="eval_bot",
        role="admin",
        permission_level="high",
        scopes=["read", "write"],
        tenant_id="eval-tenant",
    )

    # We execute queries through the rag_pipeline using mock permissions
    for case in test_cases:
        logger.info(f"Evaluating Case {case['id']}: '{case['query']}'")

        # Execute pipeline
        # Pass actor_permission explicitly. RAGPipeline will handle processing.
        payload = QueryRequest(
            query=case["query"],
            session_id=f"eval-session-{case['id']}",
            use_cache=False,
            actor_permission=mock_user.permission_level,
        )

        try:
            response = await rag_pipeline.execute(payload)

            # 2. Compute Domain-Specific metrics: Concept Recall
            answer_lower = response.answer.lower()
            expected_concepts = case.get("expected_concepts", [])
            matched_concepts = []

            for concept in expected_concepts:
                if concept.lower() in answer_lower:
                    matched_concepts.append(concept)

            concept_recall = (
                len(matched_concepts) / len(expected_concepts)
                if expected_concepts
                else 1.0
            )

            # 3. Trajectory analysis: check if tools were invoked
            executed_tools = [step.tool for step in response.trajectory if step.tool]

            # Target criteria: Faithfulness threshold
            min_score = case.get("min_faithfulness_score", 0.80)

            # We treat concept_recall as our faithfulness/relevance metric
            passed = concept_recall >= min_score

            case_result = {
                "id": case["id"],
                "query": case["query"],
                "answer": response.answer,
                "expected_concepts": expected_concepts,
                "matched_concepts": matched_concepts,
                "metrics": {
                    "concept_recall": concept_recall,
                    "target_threshold": min_score,
                    "trajectory_length": len(response.trajectory),
                    "executed_tools": executed_tools,
                },
                "passed": passed,
            }

            results.append(case_result)

            if not passed:
                failed_cases.append(case["id"])
                logger.error(
                    f"Case {case['id']} FAILED: Recall {concept_recall:.2f} < Threshold {min_score:.2f}"
                )
            else:
                logger.info(
                    f"Case {case['id']} PASSED: Recall {concept_recall:.2f} >= Threshold {min_score:.2f}"
                )

        except Exception as e:
            logger.exception(f"Exception during evaluation of case {case['id']}")
            results.append(
                {
                    "id": case["id"],
                    "query": case["query"],
                    "error": str(e),
                    "passed": False,
                }
            )
            failed_cases.append(case["id"])

    # 4. Write JSON report
    report_dir = os.path.join(os.path.dirname(__file__), "eval_results")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "offline_eval_report.json")

    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"Evaluation complete. Report written to {report_path}")

    # Return exit code based on evaluation success (For CI pipeline integration)
    if failed_cases:
        logger.error(f"Evaluation failed. Cases failed: {failed_cases}")
        return 1
    else:
        logger.info("All evaluation cases passed successfully!")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(run_evaluation())
    sys.exit(exit_code)
