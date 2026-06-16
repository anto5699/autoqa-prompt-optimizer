import logging
from datetime import datetime, timezone

from agents.state import OptimizationState, ParameterOptimizationRecord
from config import get_llm
from utils.session_store import session_store

logger = logging.getLogger(__name__)


async def csv_ingestion(state: OptimizationState) -> dict:
    """Build parameter_records from pre-parsed rules already in state.

    The route handler parses the CSV and populates conversations/rules/ground_truth_map
    in the initial state. This node initialises per-rule tracking records from those values.
    """
    session_id = state["session_id"]
    logger.info("session=%s phase=ingesting", session_id)
    session_store.update(session_id, {"current_phase": "ingesting"})

    # Resolve both model names via get_llm so env-var fallbacks are applied
    llm_config = state.get("llm_config", {})
    eval_llm = get_llm(
        model=llm_config.get("model"),
        api_key=llm_config.get("api_key"),
        base_url=llm_config.get("base_url"),
        purpose="evaluator",
    )
    opt_llm = get_llm(
        model=llm_config.get("optimizer_model") or llm_config.get("model"),
        api_key=llm_config.get("optimizer_api_key") or llm_config.get("api_key"),
        base_url=llm_config.get("optimizer_base_url") or llm_config.get("base_url"),
        purpose="optimizer",
    )
    models_used = {"evaluator": eval_llm.model_name, "optimizer": opt_llm.model_name}
    model_banner = f"Evaluation model: {eval_llm.model_name} · Reasoning model: {opt_llm.model_name}"
    session_store.update(session_id, {"models_used": models_used})
    session_store.append_log(session_id, model_banner)
    session_store.append_trace(session_id, {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "node": "csv_ingestion",
        "event": "start",
        "details": {"evaluator_model": eval_llm.model_name, "optimizer_model": opt_llm.model_name},
    })

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
            original_description=rule["description"],
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

    session_store.append_trace(session_id, {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "node": "csv_ingestion",
        "event": "end",
        "details": {"conversations": len(conversations), "rules": len(rules), "excluded": len(excluded_rules)},
    })

    return {
        "parameter_records": parameter_records,
        "current_phase": "detecting_ambiguity",
        "progress_log": [
            model_banner,
            f"CSV ingested: {len(conversations)} conversations, "
            f"{len(rules)} rules ({len(excluded_rules)} excluded)",
        ],
    }
