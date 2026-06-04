import logging

from agents.state import OptimizationState, ParameterOptimizationRecord
from utils.session_store import session_store

logger = logging.getLogger(__name__)


async def csv_ingestion(state: OptimizationState) -> dict:
    """Build parameter_records from pre-parsed rules already in state.

    The route handler parses the CSV and populates conversations/rules/ground_truth_map
    in the initial state. This node initialises per-rule tracking records from those values.
    """
    logger.info("session=%s phase=ingesting", state["session_id"])
    session_store.update(state["session_id"], {"current_phase": "ingesting"})

    rules = state["rules"]
    conversations = state["conversations"]
    excluded_rules = state["excluded_rules"]

    parameter_records: dict[str, ParameterOptimizationRecord] = {}
    for rule in rules:
        parameter_records[rule["rule_id"]] = ParameterOptimizationRecord(
            rule_id=rule["rule_id"],
            rule_type=rule["rule_type"],
            speaker=rule["speaker"],
            evaluation_type=rule["evaluation_type"],
            n_messages=rule["n_messages"],
            current_description=rule["description"],
            iteration_history=[],
            current_predictions={},
            current_accuracy=0.0,
            current_precision=0.0,
            current_recall=0.0,
            current_f1=0.0,
            true_positives=0,
            false_positives=0,
            true_negatives=0,
            false_negatives=0,
            not_applicable_count=0,
            rca_findings=None,
            optimization_notes=None,
            status="pending",
            initial_accuracy=None,
            best_accuracy=None,
            best_description=None,
        )

    logger.info(
        "session=%s conversations=%d rules=%d excluded=%d",
        state["session_id"], len(conversations), len(rules), len(excluded_rules),
    )

    return {
        "parameter_records": parameter_records,
        "current_phase": "detecting_ambiguity",
        "progress_log": [
            f"CSV ingested: {len(conversations)} conversations, "
            f"{len(rules)} rules ({len(excluded_rules)} excluded)"
        ],
    }
