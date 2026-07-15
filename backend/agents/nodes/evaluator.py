import asyncio
import json
import logging
import random
import re
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from openai import APIConnectionError, APIStatusError, RateLimitError

from agents.state import LOCKED_STATUSES, OptimizationState
from config import get_llm, settings
from utils.session_store import session_store

_MAX_BATCH_RETRIES = 5

logger = logging.getLogger(__name__)


def _verdict_from_v2_result(result: dict) -> str:
    """Map a V2 evaluator result to 'Yes' / 'No' / 'NA'. Explicit 'verdict' field wins."""
    if "verdict" in result:
        v = str(result["verdict"]).upper()
        if v == "YES":
            return "Yes"
        if v == "NO":
            return "No"
        if v == "NA":
            return "NA"
    iq = result.get("isQualified")
    if iq is True:
        return "Yes"
    if iq is False:
        return "No"
    return "NA"


def _normalize_v2_transcript(transcript: list) -> list:
    """Ensure each message has string messageId and integer timestamp for V2 payload."""
    normalized = []
    for i, msg in enumerate(transcript):
        norm = dict(msg)
        mid = norm.get("messageId")
        norm["messageId"] = str(mid) if mid is not None else str(i)
        ts = norm.get("timestamp")
        try:
            norm["timestamp"] = int(ts) if ts is not None else i
        except (TypeError, ValueError):
            norm["timestamp"] = i
        normalized.append(norm)
    return normalized


def _parse_batch_response(content: str, batch_ids: list[str]) -> tuple[list[dict], bool]:
    """Full JSON parse first; fall back to per-object regex recovery.

    Returns (results, had_parse_error) where had_parse_error=True if any rule
    could not be recovered and was defaulted. Never logs content.
    """
    try:
        result = json.loads(content)
        if isinstance(result, list):
            return result, False
    except (json.JSONDecodeError, ValueError):
        pass
    recovered: dict[str, dict] = {}
    for match in re.finditer(r'\{[^{}]+\}', content, re.DOTALL):
        try:
            obj = json.loads(match.group())
            rid = obj.get("_id")
            if rid:
                recovered[rid] = obj
        except json.JSONDecodeError:
            pass
    results = [
        recovered.get(rid, {"_id": rid, "isQualified": False, "rationale": ""})
        for rid in batch_ids
    ]
    had_error = len(recovered) < len(batch_ids)
    return results, had_error


async def evaluator(state: OptimizationState) -> dict:
    session_id = state["session_id"]
    iteration = state["current_iteration"]
    logger.info("session=%s phase=evaluating iteration=%d", session_id, iteration)
    session_store.update(session_id, {"current_phase": "evaluating", "node_progress": {"node": "evaluating", "step": 0, "total": 0}})

    records = dict(state["parameter_records"])

    # Only submit still-optimizing rules to the LLM (skip converged / stalled / label_limited)
    rules_to_evaluate = {
        rule_id: record
        for rule_id, record in records.items()
        if record.get("status") not in LOCKED_STATUSES
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
        records[rule_id] = {**records[rule_id], "current_predictions": {}, "current_rationales": {}}

    # Rebuild rules_to_evaluate to pick up the reset versions
    rules_to_evaluate = {
        rule_id: records[rule_id]
        for rule_id in rules_to_evaluate
    }

    conversations = state["conversations"]
    system_prompt = state["system_prompt"]
    system_prompt_v2 = state.get("system_prompt_v2", "")
    language = state.get("language", "en")

    llm_config = state.get("llm_config", {})
    rules_batch_size = int(llm_config.get("rules_batch_size") or settings.rules_batch_size)
    batch_size_v2 = settings.rules_batch_size_v2

    # Count V1 and V2 rules for logging
    n_v1 = sum(1 for r in rules_to_evaluate.values() if r.get("version", "v1") == "v1")
    n_v2 = sum(1 for r in rules_to_evaluate.values() if r.get("version") == "v2")
    n_batches = -(-n_v1 // rules_batch_size) if n_v1 else 0  # ceiling division
    n_v2_batches = -(-n_v2 // batch_size_v2) if n_v2 else 0

    total_conversations = len(conversations)
    session_store.update(session_id, {"node_progress": {"node": "evaluating", "step": 0, "total": total_conversations}})
    session_store.append_log(
        session_id,
        f"Iteration {iteration}: evaluating {total_conversations} conversations "
        f"(V1: {n_v1} rule(s) / {n_batches} batch(es) of {rules_batch_size}, "
        f"V2: {n_v2} rule(s) / {n_v2_batches} batch(es) of {batch_size_v2}, "
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
        "details": {"iteration": iteration, "conversations": total_conversations, "rules": len(rules_to_evaluate), "v1_batches_per_conversation": n_batches, "v2_batches_per_conversation": n_v2_batches},
    })
    semaphore = asyncio.Semaphore(settings.max_concurrent_llm_calls)
    completed = 0

    async def evaluate_and_track(conv: dict[str, Any]) -> tuple[str, list]:
        nonlocal completed
        try:
            return await _evaluate_conversation(
                conv, rules_to_evaluate, system_prompt, system_prompt_v2,
                language, llm, semaphore, rules_batch_size, batch_size_v2,
            )
        finally:
            completed += 1
            session_store.set_node_progress(session_id, "evaluating", completed, total_conversations)

    tasks = [evaluate_and_track(conv) for conv in conversations]
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
                records[rule_id]["current_rationales"][conv_id] = ""
            continue

        _, rule_results = result
        for rule_result in rule_results:
            rule_id = rule_result.get("_id")
            if rule_id and rule_id in rules_to_evaluate:
                if "_dynamic_combined" in rule_result:
                    records[rule_id]["current_predictions"][conv_id] = rule_result["_dynamic_combined"]
                elif "_v2_verdict" in rule_result:
                    records[rule_id]["current_predictions"][conv_id] = rule_result["_v2_verdict"]
                else:
                    is_qualified = rule_result.get("isQualified", False)
                    records[rule_id]["current_predictions"][conv_id] = "Yes" if is_qualified else "No"
                records[rule_id]["current_rationales"][conv_id] = (rule_result.get("rationale") or "")[:500]

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
    system_prompt_v2: str,
    language: str,
    llm,
    semaphore: asyncio.Semaphore,
    batch_size: int,                # V1 batch size (from settings.rules_batch_size)
    batch_size_v2: int = 4,         # V2 batch size (from settings.rules_batch_size_v2)
) -> tuple[str, list]:
    conv_id = conv["conversation_id"]

    # Partition records by version; skip converged rules
    v1_records = {
        rid: rec for rid, rec in parameter_records.items()
        if rec.get("version", "v1") == "v1" and rec.get("status") not in LOCKED_STATUSES
    }
    v2_records = {
        rid: rec for rid, rec in parameter_records.items()
        if rec.get("version") == "v2" and rec.get("status") not in LOCKED_STATUSES
    }

    n_v1_batches = -(-len(v1_records) // batch_size) if v1_records else 0
    n_v2_batches = -(-len(v2_records) // batch_size_v2) if v2_records else 0
    logger.info(
        "conversation_id=%s evaluator: V1: %d rule(s) / %d batch(es) (batch=%d), V2: %d rule(s) / %d batch(es) (batch=%d)",
        conv_id, len(v1_records), n_v1_batches, batch_size,
        len(v2_records), n_v2_batches, batch_size_v2,
    )

    all_rule_results: list[dict] = []

    # ── V1 batching loop (unchanged logic) ──────────────────────────────────
    v1_rule_ids = list(v1_records.keys())
    for i in range(0, len(v1_rule_ids), batch_size):
        batch_ids = v1_rule_ids[i:i + batch_size]

        # Build payload; dynamic rules expand to two items (trigger + answer) with temp IDs
        batch_payload = []
        expanded_ids: list[str] = []
        for rid in batch_ids:
            record = v1_records[rid]
            if record.get("rule_type") == "dynamic":
                batch_payload.append({
                    "description": record.get("trigger_description") or "",
                    "speaker": record.get("trigger_speaker") or "customer",
                    "id": f"{rid}__trigger",
                    "evaluation_type": record["evaluation_type"],
                    "n_messages": record["n_messages"],
                })
                expanded_ids.append(f"{rid}__trigger")
                batch_payload.append({
                    "description": record["current_description"],
                    "speaker": record["speaker"],
                    "id": f"{rid}__answer",
                    "evaluation_type": record["evaluation_type"],
                    "n_messages": record["n_messages"],
                })
                expanded_ids.append(f"{rid}__answer")
            else:
                batch_payload.append({
                    "description": record["current_description"],
                    "speaker": record["speaker"],
                    "id": rid,
                    "evaluation_type": record["evaluation_type"],
                    "n_messages": record["n_messages"],
                })
                expanded_ids.append(rid)

        user_content = (
            f"Transcripts: {json.dumps(conv['transcript'])}\n"
            f"Rules: {json.dumps(batch_payload)}\n"
            f"Language: {language}"
        )

        response = None
        for attempt in range(_MAX_BATCH_RETRIES + 1):
            try:
                async with semaphore:
                    response = await asyncio.wait_for(
                        llm.ainvoke([
                            SystemMessage(content=system_prompt),
                            HumanMessage(content=user_content),
                        ]),
                        timeout=settings.llm_call_timeout,
                    )
                break  # success
            except asyncio.TimeoutError:
                logger.warning(
                    "conversation_id=%s v1_batch=%d timed out after %ds — defaulting batch rules to Not Adhered",
                    conv_id, i // batch_size + 1, settings.llm_call_timeout,
                )
                break
            except (RateLimitError, APIConnectionError) as exc:
                if attempt < _MAX_BATCH_RETRIES:
                    wait = min(60, (2 ** attempt) + random.random())
                    logger.info(
                        "conversation_id=%s v1_batch=%d retryable error (%s) — retry %d/%d in %.1fs",
                        conv_id, i // batch_size + 1, type(exc).__name__, attempt + 1, _MAX_BATCH_RETRIES, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.warning(
                        "conversation_id=%s v1_batch=%d exhausted %d retries (%s: %s) — defaulting to Not Adhered",
                        conv_id, i // batch_size + 1, _MAX_BATCH_RETRIES, type(exc).__name__, exc,
                    )
                    break
            except APIStatusError as exc:
                if exc.status_code == 503 and attempt < _MAX_BATCH_RETRIES:
                    wait = min(60, (2 ** attempt) + random.random())
                    logger.info(
                        "conversation_id=%s v1_batch=%d 503 Service Unavailable — retry %d/%d in %.1fs",
                        conv_id, i // batch_size + 1, attempt + 1, _MAX_BATCH_RETRIES, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.warning(
                        "conversation_id=%s v1_batch=%d non-retryable API error (%d: %s) — defaulting to Not Adhered",
                        conv_id, i // batch_size + 1, exc.status_code, exc,
                    )
                    break
            except Exception as exc:
                logger.warning(
                    "conversation_id=%s v1_batch=%d unexpected error (%s: %s) — defaulting to Not Adhered",
                    conv_id, i // batch_size + 1, type(exc).__name__, exc,
                )
                break

        if response is None:
            batch_results = [{"_id": rid, "isQualified": False, "rationale": ""} for rid in batch_ids]
            all_rule_results.extend(batch_results)
            continue

        raw_results, had_parse_error = _parse_batch_response(response.content, expanded_ids)
        if had_parse_error:
            logger.warning(
                "conversation_id=%s v1_batch=%d JSON parse failure — some rules defaulted to Not Adhered",
                conv_id, i // batch_size + 1,
            )

        # Combine dynamic rule results (trigger+answer → Yes/No/NA); pass through others unchanged
        by_expanded = {r["_id"]: r for r in raw_results}
        batch_results = []
        for rid in batch_ids:
            record = v1_records[rid]
            if record.get("rule_type") == "dynamic":
                trigger_r = by_expanded.get(f"{rid}__trigger", {"isQualified": False, "rationale": ""})
                answer_r = by_expanded.get(f"{rid}__answer", {"isQualified": False, "rationale": ""})
                if not trigger_r.get("isQualified", False):
                    combined = "NA"
                    rationale = trigger_r.get("rationale", "")
                else:
                    combined = "Yes" if answer_r.get("isQualified", False) else "No"
                    rationale = answer_r.get("rationale", "")
                batch_results.append({"_id": rid, "_dynamic_combined": combined, "rationale": rationale})
            else:
                batch_results.append(by_expanded.get(rid, {"_id": rid, "isQualified": False, "rationale": ""}))

        all_rule_results.extend(batch_results)

    # ── V2 batching loop ─────────────────────────────────────────────────────
    v2_transcript = _normalize_v2_transcript(conv.get("transcript", []))
    v2_rule_ids = list(v2_records.keys())
    for i in range(0, len(v2_rule_ids), batch_size_v2):
        batch_ids = v2_rule_ids[i:i + batch_size_v2]

        batch_payload = []
        for rid in batch_ids:
            rec = v2_records[rid]
            batch_payload.append({
                "description": rec["current_description"],
                "speaker": rec["speaker"],
                "id": rid,
                "evaluation_type": rec["evaluation_type"],
                "n_messages": rec["n_messages"],
            })

        user_content = (
            f"Transcripts: {json.dumps(v2_transcript)}\n"
            f"Rules: {json.dumps(batch_payload)}\n"
            f"Language: {language}"
        )

        response = None
        for attempt in range(_MAX_BATCH_RETRIES + 1):
            try:
                async with semaphore:
                    response = await asyncio.wait_for(
                        llm.ainvoke([
                            SystemMessage(content=system_prompt_v2),
                            HumanMessage(content=user_content),
                        ]),
                        timeout=settings.llm_call_timeout,
                    )
                break  # success
            except asyncio.TimeoutError:
                logger.warning(
                    "conversation_id=%s v2_batch=%d timed out after %ds — defaulting batch rules to Not Adhered",
                    conv_id, i // batch_size_v2 + 1, settings.llm_call_timeout,
                )
                break
            except (RateLimitError, APIConnectionError) as exc:
                if attempt < _MAX_BATCH_RETRIES:
                    wait = min(60, (2 ** attempt) + random.random())
                    logger.info(
                        "conversation_id=%s v2_batch=%d retryable error (%s) — retry %d/%d in %.1fs",
                        conv_id, i // batch_size_v2 + 1, type(exc).__name__, attempt + 1, _MAX_BATCH_RETRIES, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.warning(
                        "conversation_id=%s v2_batch=%d exhausted %d retries (%s: %s) — defaulting to Not Adhered",
                        conv_id, i // batch_size_v2 + 1, _MAX_BATCH_RETRIES, type(exc).__name__, exc,
                    )
                    break
            except APIStatusError as exc:
                if exc.status_code == 503 and attempt < _MAX_BATCH_RETRIES:
                    wait = min(60, (2 ** attempt) + random.random())
                    logger.info(
                        "conversation_id=%s v2_batch=%d 503 Service Unavailable — retry %d/%d in %.1fs",
                        conv_id, i // batch_size_v2 + 1, attempt + 1, _MAX_BATCH_RETRIES, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.warning(
                        "conversation_id=%s v2_batch=%d non-retryable API error (%d: %s) — defaulting to Not Adhered",
                        conv_id, i // batch_size_v2 + 1, exc.status_code, exc,
                    )
                    break
            except Exception as exc:
                logger.warning(
                    "conversation_id=%s v2_batch=%d unexpected error (%s: %s) — defaulting to Not Adhered",
                    conv_id, i // batch_size_v2 + 1, type(exc).__name__, exc,
                )
                break

        if response is None:
            batch_results = [{"_id": rid, "_v2_verdict": "No", "rationale": ""} for rid in batch_ids]
            all_rule_results.extend(batch_results)
            continue

        raw_results, had_parse_error = _parse_batch_response(response.content, batch_ids)
        if had_parse_error:
            logger.warning(
                "conversation_id=%s v2_batch=%d JSON parse failure — some rules defaulted to Not Adhered",
                conv_id, i // batch_size_v2 + 1,
            )

        by_id = {r["_id"]: r for r in raw_results}
        batch_results = []
        for rid in batch_ids:
            result = by_id.get(rid, {"_id": rid, "isQualified": False})
            rationale = (result.get("justification") or result.get("rationale") or "")[:500]
            verdict = _verdict_from_v2_result(result)
            batch_results.append({"_id": rid, "_v2_verdict": verdict, "rationale": rationale})

        all_rule_results.extend(batch_results)

    return conv_id, all_rule_results
