import argparse
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


def evaluate_answer_and_trajectory(query: str, answer: str, trajectory: list, case_data: dict) -> dict:
    """Helper to evaluate a specific answer and its execution trajectory against gold standards."""
    answer_lower = answer.lower()
    expected_concepts = case_data.get("expected_concepts", [])
    matched_concepts = []

    # Calculate concept recall
    for concept in expected_concepts:
        if concept.lower() in answer_lower:
            matched_concepts.append(concept)

    concept_recall = len(matched_concepts) / len(expected_concepts) if expected_concepts else 1.0

    # Extract executed tools from trajectory steps
    executed_tools = []
    for step in trajectory:
        # Support both Pydantic model items and raw dictionaries
        tool = getattr(step, "tool", None) or (step.get("tool") if isinstance(step, dict) else None)
        if tool:
            executed_tools.append(tool)

    min_score = case_data.get("min_faithfulness_score", 0.80)
    passed = concept_recall >= min_score

    return {
        "concept_recall": concept_recall,
        "matched_concepts": matched_concepts,
        "executed_tools": executed_tools,
        "target_threshold": min_score,
        "passed": passed,
    }


async def run_active_evaluation(test_cases: list) -> list:
    """Executes fresh queries through the pipeline and evaluates them."""
    results = []

    mock_user = User(
        username="eval_bot", role="admin", permission_level="high", scopes=["read", "write"], tenant_id="eval-tenant"
    )

    for case in test_cases:
        logger.info(f"Evaluating Case {case['id']}: '{case['query']}'")

        payload = QueryRequest(
            query=case["query"],
            session_id=f"eval-session-{case['id']}",
            use_cache=False,
            actor_permission=mock_user.permission_level,
        )

        try:
            response = await rag_pipeline.execute(payload)
            eval_metrics = evaluate_answer_and_trajectory(payload.query, response.answer, response.trajectory, case)

            results.append(
                {
                    "id": case["id"],
                    "query": case["query"],
                    "answer": response.answer,
                    "expected_concepts": case.get("expected_concepts", []),
                    "matched_concepts": eval_metrics["matched_concepts"],
                    "metrics": {
                        "concept_recall": eval_metrics["concept_recall"],
                        "target_threshold": eval_metrics["target_threshold"],
                        "trajectory_length": len(response.trajectory),
                        "executed_tools": eval_metrics["executed_tools"],
                    },
                    "passed": eval_metrics["passed"],
                }
            )

            if not eval_metrics["passed"]:
                logger.error(
                    f"Case {case['id']} FAILED: Recall {eval_metrics['concept_recall']:.2f} < Threshold {eval_metrics['target_threshold']:.2f}"
                )
            else:
                logger.info(
                    f"Case {case['id']} PASSED: Recall {eval_metrics['concept_recall']:.2f} >= Threshold {eval_metrics['target_threshold']:.2f}"
                )

        except Exception as e:
            logger.exception(f"Exception during evaluation of case {case['id']}")
            results.append({"id": case["id"], "query": case["query"], "error": str(e), "passed": False})

    return results


def run_historical_evaluation(test_cases: list) -> list:
    """Parses historical JSONL trajectories and computes evaluation metrics post-hoc."""
    logger.info("Starting evaluation over historical JSONL trajectories...")
    results = []

    trajectory_file = os.path.join(os.path.dirname(__file__), "eval_results", "trajectory_runs.jsonl")
    if not os.path.exists(trajectory_file):
        logger.warning(f"No historical trajectory log found at {trajectory_file}. Execute runs first.")
        return []

    # Map test cases by query keywords for fuzzy matching
    case_map = {case["query"].lower(): case for case in test_cases}

    with open(trajectory_file, "r") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                run_data = json.loads(line)
                query = run_data.get("query", "")
                answer = run_data.get("final_answer") or run_data.get("answer") or ""
                trajectory = run_data.get("trajectory", [])

                # Check if this query matches any of our golden test cases
                matched_case = None
                for q_key, case in case_map.items():
                    q_normalized = q_key.strip("?. ").lower()
                    query_normalized = query.strip("?. ").lower()
                    if q_normalized == query_normalized:
                        matched_case = case
                        break

                if matched_case:
                    eval_metrics = evaluate_answer_and_trajectory(query, answer, trajectory, matched_case)
                    results.append(
                        {
                            "run_id": run_data.get("session_id", f"run_{line_num}"),
                            "query": query,
                            "expected_concepts": matched_case.get("expected_concepts", []),
                            "matched_concepts": eval_metrics["matched_concepts"],
                            "metrics": {
                                "concept_recall": eval_metrics["concept_recall"],
                                "target_threshold": eval_metrics["target_threshold"],
                                "executed_tools": eval_metrics["executed_tools"],
                            },
                            "passed": eval_metrics["passed"],
                        }
                    )
            except Exception as e:
                logger.error(f"Failed to parse line {line_num} in trajectory log: {e}")

    logger.info(f"Processed {len(results)} historical trajectory matches.")
    return results


async def main():
    parser = argparse.ArgumentParser(description="Offline RAG Evaluation Pipeline")
    parser.add_argument(
        "--historical",
        action="store_true",
        help="Run evaluation over historical JSONL trajectories instead of active calls",
    )
    args = parser.parse_args()

    # Load golden dataset
    dataset_path = os.path.join(os.path.dirname(__file__), "golden_dataset.json")
    with open(dataset_path, "r") as f:
        test_cases = json.load(f)

    if args.historical:
        results = run_historical_evaluation(test_cases)
        report_name = "historical_eval_report.json"
    else:
        results = await run_active_evaluation(test_cases)
        report_name = "offline_eval_report.json"

    report_dir = os.path.join(os.path.dirname(__file__), "eval_results")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, report_name)

    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"Report written to: {report_path}")

    # Calculate exit status
    if not results:
        sys.exit(0)

    failures = [r for r in results if not r.get("passed", False)]
    if failures:
        logger.error(f"Evaluation FAILED: {len(failures)} cases did not meet quality thresholds.")
        sys.exit(1)
    else:
        logger.info("All evaluation runs met the required quality thresholds.")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
