import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agents.state import OptimizationState
from config import get_llm, settings
from utils.session_store import session_store

logger = logging.getLogger(__name__)


async def evaluator(state: OptimizationState) -> dict:
    session_id = state["session_id"]
    iteration = state["current_iteration"]
    logger.info("session=%s phase=evaluating iteration=%d", session_id, iteration)
    session_store.update(session_id, {"current_phase": "evaluating"})

    records = dict(state["parameter_records"])

    # Only submit non-converged rules to the LLM
    rules_to_evaluate = {
        rule_id: record
        for rule_id, record in records.items()
        if record.get("status") != "converged"
    }

    # Early return before any mutations if all rules are already converged
    if not rules_to_evaluate:
        session_store.append_log(session_id, f"Iteration {iteration}: all rules converged, evaluation skipped")
        return {
            "parameter_records": records,
            "current_phase": "benchmarking",
            "progress_log": [f"Iteration {iteration}: all rules converged, evaluation skipped"],
        }

    # Reset predictions only for non-converged rules (after early-return check to avoid
    # mutating state when we won't be running evaluation).
    # Converged rules keep last-known predictions to prevent LLM non-determinism regression.
    for rule_id in list(rules_to_evaluate.keys()):
        records[rule_id] = {**records[rule_id], "current_predictions": {}}

    # Rebuild rules_to_evaluate to pick up the reset versions
    rules_to_evaluate = {
        rule_id: records[rule_id]
        for rule_id in rules_to_evaluate
    }

    conversations = state["conversations"]
    system_prompt = state["system_prompt"]
    language = state.get("language", "en")

    llm_config = state.get("llm_config", {})
    rules_batch_size = int(llm_config.get("rules_batch_size") or settings.rules_batch_size)
    n_batches = -(-len(rules_to_evaluate) // rules_batch_size)  # ceiling division

    session_store.append_log(
        session_id,
        f"Iteration {iteration}: evaluating {len(conversations)} conversations "
        f"({len(rules_to_evaluate)} active rules → {n_batches} batch(es) of {rules_batch_size} per conversation, "
        f"{len(records) - len(rules_to_evaluate)} converged/locked)…",
    )

    llm = get_llm(
        model=llm_config.get("model"),
        api_key=llm_config.get("api_key"),
        base_url=llm_config.get("base_url"),
    )
    session_store.append_trace(session_id, {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "node": "evaluator", "model": llm.model_name, "event": "start",
        "details": {"iteration": iteration, "conversations": len(conversations), "rules": len(rules_to_evaluate), "batches_per_conversation": n_batches},
    })
    semaphore = asyncio.Semaphore(settings.max_concurrent_llm_calls)

    async def evaluate_one(conv: dict[str, Any]) -> tuple[str, list]:
        return await _evaluate_conversation(conv, rules_to_evaluate, system_prompt, language, llm, semaphore, rules_batch_size)

    tasks = [evaluate_one(conv) for conv in conversations]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    failure_count = 0
    for conv, result in zip(conversations, results):
        conv_id = conv["conversation_id"]
        if isinstance(result, Exception):
            failure_count += 1
            logger.warning(
                "session=%s conversation_id=%s evaluation error: %s",
                session_id, conv_id, result,
            )
            for rule_id in rules_to_evaluate:
                records[rule_id]["current_predictions"][conv_id] = "No"
            continue

        _, rule_results = result
        for rule_result in rule_results:
            rule_id = rule_result.get("_id")
            if rule_id and rule_id in rules_to_evaluate:
                is_qualified = rule_result.get("isQualified", False)
                records[rule_id]["current_predictions"][conv_id] = "Yes" if is_qualified else "No"

    if failure_count == len(conversations):
        raise RuntimeError(
            f"Evaluation failed: all {len(conversations)} conversation LLM calls returned errors"
        )

    failure_note = (
        [f"WARNING: {failure_count}/{len(conversations)} conversation(s) failed LLM evaluation — defaulted to Not Adhered"]
        if failure_count
        else []
    )

    return {
        "parameter_records": records,
        "current_phase": "benchmarking",
        "progress_log": [
            f"Iteration {iteration}: evaluated {len(conversations)} conversations "
            f"({len(rules_to_evaluate)} rules, {n_batches} batch(es) of {rules_batch_size} per conversation)"
        ] + failure_note,
    }


async def _evaluate_conversation(
    conv: dict,
    parameter_records: dict,
    system_prompt: str,
    language: str,
    llm,
    semaphore: asyncio.Semaphore,
    batch_size: int,
) -> tuple[str, list]:
    conv_id = conv["conversation_id"]

    rule_ids = list(parameter_records.keys())
    all_rule_results: list[dict] = []

    for i in range(0, len(rule_ids), batch_size):
        batch_ids = rule_ids[i:i + batch_size]
        batch_payload = [
            {
                "description": parameter_records[rid]["current_description"],
                "speaker": parameter_records[rid]["speaker"],
                "id": parameter_records[rid]["rule_id"],
                "evaluation_type": parameter_records[rid]["evaluation_type"],
                "n_messages": parameter_records[rid]["n_messages"],
            }
            for rid in batch_ids
        ]

        user_content = (
            f"Transcripts: {json.dumps(conv['transcript'])}\n"
            f"Rules: {json.dumps(batch_payload)}\n"
            f"Language: {language}"
        )

        async with semaphore:
            response = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content),
            ])

        try:
            batch_results = json.loads(response.content)
            if not isinstance(batch_results, list):
                raise ValueError("Expected JSON array")
        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "conversation_id=%s batch=%d JSON parse failure — defaulting batch rules to No",
                conv_id, i // batch_size + 1,
            )
            batch_results = [{"_id": rid, "isQualified": False} for rid in batch_ids]

        all_rule_results.extend(batch_results)

    return conv_id, all_rule_results
