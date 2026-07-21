import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from agents.state import ClarifyingQuestion, OptimizationState
from config import get_llm, settings
from utils.session_store import session_store

logger = logging.getLogger(__name__)

_LABEL_MAP = {
    "yes": "Yes", "adhered": "Yes", "y": "Yes", "true": "Yes",
    "no": "No", "not adhered": "No", "n": "No", "false": "No",
    "na": "NA", "n/a": "NA", "not applicable": "NA",
}

_JUDGE_SYSTEM = (
    "You are a QA ground-truth auditor. For each rule, decide the CORRECT judgment for this "
    "conversation strictly according to the rule's own definition — not what a human "
    "reviewer might have labelled it. Never compute or state a final Yes/No/NA label yourself — "
    "only report the booleans below plus a reason; the label is derived from your booleans "
    "downstream.\n\n"
    "For V1 DYNAMIC rules (with a trigger definition): set trigger_present to true or false — "
    "whether the trigger/scope condition is present in this conversation. If false, the rule "
    "does not apply and answer_met is irrelevant (leave it null). Only if trigger_present is "
    "true do you also set answer_met: true if the agent's response meets the answer definition, "
    "false if it does not.\n"
    "For V1 STATIC rules (no trigger definition given): leave trigger_present null, and always "
    "set answer_met: true or false from the definition.\n\n"
    "For V2 unified rules (description has CONDITION / EXPECTED BEHAVIOR / PROHIBITED (optional) "
    "/ EXCEPTION sections), evaluate in this exact order and report all four fields:\n"
    "  1. exception_present: true if any EXCEPTION item is satisfied (evaluation is impossible), "
    "else false. 'None.' in the EXCEPTION section always means false.\n"
    "  2. prohibited_observed: true if the evaluated speaker performed any PROHIBITED action, "
    "else false. If the rule has no PROHIBITED section, always set this to false.\n"
    "  3. condition_met: true if CONDITION is satisfied ('Always.' is always satisfied), else "
    "false.\n"
    "  4. expected_behavior_met: true if EXPECTED BEHAVIOR was fully satisfied by the evaluated "
    "speaker, else false. Judge this even if you expect exception/prohibited/condition to "
    "override it downstream — always report your honest assessment of all four fields.\n"
    "Leave trigger_present and answer_met null for V2 rules.\n\n"
    "Judge only from explicit content in the transcript text. Do not infer tone, prosody, or "
    "off-transcript actions. Give a one-sentence reason (max 40 words) that PARAPHRASES the "
    "evidence for your decision — never quote the transcript verbatim."
)

_SYNTH_SYSTEM = (
    "You are a QA evaluation expert. You are given, for one rule, how often the recorded ground "
    "truth labels disagree with a careful reading of the rule's own definition across ALL "
    "conversations. Classify the gap between the description and the labels.\n\n"
    "Classify the gap type:\n"
    "  DESCRIPTION_MISMATCH: The labels systematically reward a criterion the description does "
    "not capture (the disagreements share a consistent direction/theme).\n"
    "  NO_GAP: The description matches what the labels reward; disagreements are few or absent.\n"
    "  LABELLING_INCONSISTENCY: Disagreements are scattered and contradictory — the data itself "
    "is noisy, the description is not the problem.\n\n"
    "Only report patterns evidenced by the provided summary. Use plain English — no markdown, "
    "no asterisks."
)


def _normalize_label(value) -> str:
    return _LABEL_MAP.get(str(value or "").strip().lower(), "NA")


def _to_bool(value):
    """Coerce a JSON boolean or its string/None variants. Returns None if unparseable."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "yes", "y"):
            return True
        if s in ("false", "no", "n"):
            return False
    return None


def _derive_should_be(is_dynamic: bool, obj: dict) -> str | None:
    """Compute the definition-correct label from independent trigger/answer booleans.

    The LLM is never trusted to emit the final Yes/No/NA token directly — that token is
    the one place a single free-text generation could contradict its own reasoning. Instead
    we derive it in code from two separately-judged booleans. Returns None when the model's
    output can't support a derivation (caller should drop the case rather than guess).
    """
    if is_dynamic:
        trigger_present = _to_bool(obj.get("trigger_present"))
        if trigger_present is False:
            return "NA"
        if trigger_present is True:
            answer_met = _to_bool(obj.get("answer_met"))
            if answer_met is True:
                return "Yes"
            if answer_met is False:
                return "No"
        return None
    answer_met = _to_bool(obj.get("answer_met"))
    if answer_met is True:
        return "Yes"
    if answer_met is False:
        return "No"
    return None


def _derive_should_be_v2(obj: dict) -> str | None:
    """V2 unified-rule derivation, mirroring the production evaluator's own decision order
    (backend/config.py DEFAULT_SYSTEM_PROMPT_V2 "DECISION LOGIC"): EXCEPTION, then PROHIBITED,
    then CONDITION, then EXPECTED BEHAVIOR. Returns None when a required field is missing.
    """
    exception_present = _to_bool(obj.get("exception_present"))
    if exception_present is None:
        return None
    if exception_present:
        return "NA"
    prohibited_observed = _to_bool(obj.get("prohibited_observed"))
    if prohibited_observed:
        return "No"
    condition_met = _to_bool(obj.get("condition_met"))
    if condition_met is None:
        return None
    if not condition_met:
        return "NA"
    expected_behavior_met = _to_bool(obj.get("expected_behavior_met"))
    if expected_behavior_met is True:
        return "Yes"
    if expected_behavior_met is False:
        return "No"
    return None


def diff_cases(
    conv_verdicts: list[tuple[str, dict]],
    ground_truth_map: dict,
    rule_ids: list[str],
) -> dict[str, list[dict]]:
    """Diff per-conversation audit verdicts against ground truth → flagged cases per rule.

    A case is flagged only when the definition-correct label (`should_be`) differs from the
    recorded ground truth. Conversations with no GT entry for a rule are skipped. Pure function.
    """
    pre_audit_cases: dict[str, list[dict]] = {rid: [] for rid in rule_ids}
    for conv_id, verdicts in conv_verdicts:
        gt_by_rule = ground_truth_map.get(conv_id, {})
        for rule_id, verdict in verdicts.items():
            if rule_id not in pre_audit_cases:
                continue
            current_gt = gt_by_rule.get(rule_id)
            if current_gt is None:
                continue
            should_be = _normalize_label(verdict.get("should_be"))
            if should_be != current_gt:
                pre_audit_cases[rule_id].append({
                    "conversation_id": conv_id,
                    "current_gt": current_gt,
                    "should_be": should_be,
                    "reason": str(verdict.get("reason") or "").strip()[:220],
                    # Change 3: consensus confidence (1.0 for single-judge runs)
                    "confidence": round(float(verdict.get("confidence", 1.0)), 4),
                })
    return pre_audit_cases


def _consensus_verdicts(
    runs_results: list[list[tuple[str, dict]]], rule_ids: list[str]
) -> list[tuple[str, dict]]:
    """Merge K judge passes into one verdict per (conversation, rule) via majority vote.

    confidence = votes_for_winner / K. Tie → the primary run's label (deterministic). With K==1
    this returns the single run's verdicts unchanged, each with confidence 1.0. Pure function.
    """
    from collections import Counter

    per_conv: dict[str, list[dict]] = {}
    order: list[str] = []
    for run in runs_results:
        for conv_id, verdicts in run:
            if conv_id not in per_conv:
                per_conv[conv_id] = []
                order.append(conv_id)
            per_conv[conv_id].append(verdicts or {})

    n_runs = len(runs_results) or 1
    out: list[tuple[str, dict]] = []
    for conv_id in order:
        vlist = per_conv[conv_id]
        merged: dict[str, dict] = {}
        for rid in rule_ids:
            labels: list[str] = []
            reasons: dict[str, str] = {}
            for v in vlist:
                obj = v.get(rid)
                if not obj:
                    continue
                lab = _normalize_label(obj.get("should_be"))
                labels.append(lab)
                reasons.setdefault(lab, str(obj.get("reason") or ""))
            if not labels:
                continue
            counts = Counter(labels)
            best_count = counts.most_common(1)[0][1]
            winners = [lab for lab, c in counts.items() if c == best_count]
            primary_obj = vlist[0].get(rid) if vlist else None
            primary = _normalize_label(primary_obj.get("should_be")) if primary_obj else None
            winner = primary if primary in winners else winners[0]
            merged[rid] = {
                "should_be": winner,
                "reason": reasons.get(winner, ""),
                "confidence": round(best_count / n_runs, 4),
            }
        out.append((conv_id, merged))
    return out


def _format_transcript(messages: list) -> str:
    lines = []
    for m in messages:
        speaker = str(m.get("speaker", "unknown")).title()
        lines.append(f"  {speaker}: {m.get('msg', '')}")
    return "\n".join(lines) if lines else "  (no transcript)"


def _rule_definition_block(rule: dict) -> str:
    """Human-readable definition for one rule, used inside the judgement prompt."""
    rule_id = rule["rule_id"]
    if rule.get("version") == "v2":
        return (
            f"Rule ID: {rule_id}\n"
            "Type: V2 unified rule (CONDITION / EXPECTED BEHAVIOR / PROHIBITED (optional) / "
            "EXCEPTION embedded below)\n"
            f"Description:\n{rule.get('description', '')}"
        )
    is_dynamic = rule.get("rule_type") == "dynamic"
    lines = [
        f"Rule ID: {rule_id}",
        f"Type: {'dynamic (has a trigger/scope condition)' if is_dynamic else 'static'}",
    ]
    if is_dynamic:
        lines.append(f"Trigger / scope definition (is the rule applicable?):\n{rule.get('trigger_description') or '(none)'}")
    lines.append(f"Answer definition (did the agent adhere?):\n{rule.get('description', '')}")
    return "\n".join(lines)


def _parse_verdicts(content: str, rule_ids: list[str]) -> dict[str, dict]:
    """Full JSON parse first; fall back to per-object regex recovery. Never logs content."""
    parsed: dict[str, dict] = {}

    def _absorb(items):
        if isinstance(items, list):
            for obj in items:
                if isinstance(obj, dict) and obj.get("rule_id") in rule_ids:
                    parsed[obj["rule_id"]] = obj

    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        _absorb(json.loads(raw))
    except (json.JSONDecodeError, ValueError):
        for match in re.finditer(r"\{[^{}]+\}", content, re.DOTALL):
            try:
                obj = json.loads(match.group())
                if isinstance(obj, dict) and obj.get("rule_id") in rule_ids:
                    parsed[obj["rule_id"]] = obj
            except json.JSONDecodeError:
                pass
    return parsed


async def pre_flight_gt_audit(state: OptimizationState) -> dict:
    """Per-conversation GT alignment audit over ALL conversations, runs once after csv_ingestion.

    For every conversation we ask the model for the definition-correct label of every rule,
    then flag conversations where that disagrees with the recorded ground truth. Findings are
    surfaced per metric as a table plus an actionable "apply these relabels?" question.
    """
    session_id = state["session_id"]
    rules = state["rules"]
    ground_truth_map = state["ground_truth_map"]
    conversations = state["conversations"]
    rule_ids = [r["rule_id"] for r in rules]
    rules_by_id = {r["rule_id"]: r for r in rules}

    session_store.update(session_id, {
        "current_phase": "analyzing_failures",
        "node_progress": {"node": "gt_audit", "step": 0, "total": len(conversations)},
    })
    session_store.append_log(
        session_id,
        f"Pre-flight GT audit: checking {len(rules)} rule(s) against {len(conversations)} conversation(s)…",
    )

    llm_config = state.get("llm_config", {})
    llm = get_llm(
        model=llm_config.get("optimizer_model") or llm_config.get("model"),
        api_key=llm_config.get("optimizer_api_key") or llm_config.get("api_key"),
        base_url=llm_config.get("optimizer_base_url") or llm_config.get("base_url"),
        purpose="optimizer",
    )
    session_store.append_trace(session_id, {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "node": "pre_flight_gt_audit", "model": llm.model_name, "event": "start",
        "details": {"rules": len(rules), "conversations": len(conversations)},
    })

    definitions_block = "\n\n".join(_rule_definition_block(r) for r in rules)
    sem = asyncio.Semaphore(settings.max_concurrent_llm_calls)

    # Consensus judges (Change 3): default 1 run == today's single-model audit. Additional runs
    # use a distinct model when configured (genuine independence), else resample the primary model.
    runs = max(1, min(5, settings.gt_audit_consensus_runs))
    consensus_model = (settings.gt_audit_consensus_model or "").strip()
    judge_llms = [llm]
    for _ in range(runs - 1):
        judge_llms.append(get_llm(
            model=consensus_model,
            api_key=llm_config.get("optimizer_api_key") or llm_config.get("api_key"),
            base_url=llm_config.get("optimizer_base_url") or llm_config.get("base_url"),
            purpose="optimizer",
        ) if consensus_model else llm)
    total_calls = runs * len(conversations)
    completed = 0

    async def _judge_conversation(conv: dict, judge_llm) -> tuple[str, dict[str, dict]]:
        nonlocal completed
        conv_id = conv["conversation_id"]
        prompt = (
            f"Conversation transcript:\n{_format_transcript(conv.get('transcript', []))}\n\n"
            f"Rules to judge:\n{definitions_block}\n\n"
            "For EACH rule, report the fields relevant to its type (V1 dynamic: trigger_present "
            "+ answer_met; V1 static: answer_met only; V2 unified: exception_present, "
            "prohibited_observed, condition_met, expected_behavior_met), plus a one-sentence "
            "reason. Leave irrelevant fields null.\n"
            "Respond with ONLY a JSON array, one object per rule:\n"
            '[{"rule_id": "<id>", "trigger_present": true|false|null, '
            '"answer_met": true|false|null, "exception_present": true|false|null, '
            '"prohibited_observed": true|false|null, "condition_met": true|false|null, '
            '"expected_behavior_met": true|false|null, "reason": "<paraphrased, max 40 words>"}]'
        )
        try:
            async with sem:
                response = await asyncio.wait_for(
                    judge_llm.ainvoke([
                        SystemMessage(content=_JUDGE_SYSTEM),
                        HumanMessage(content=prompt),
                    ]),
                    timeout=settings.llm_call_timeout,
                )
            verdicts = _parse_verdicts(response.content, rule_ids)
            for rule_id in list(verdicts.keys()):
                obj = verdicts[rule_id]
                rule = rules_by_id.get(rule_id, {})
                if rule.get("version") == "v2":
                    derived = _derive_should_be_v2(obj)
                else:
                    derived = _derive_should_be(rule.get("rule_type") == "dynamic", obj)
                if derived is None:
                    # Model didn't supply enough to derive a label — drop rather than guess.
                    del verdicts[rule_id]
                    continue
                obj["should_be"] = derived
        except Exception as exc:  # noqa: BLE001 — audit must not crash the run
            logger.warning("session=%s conversation audit failed (%s) — skipping", session_id, type(exc).__name__)
            verdicts = {}
        finally:
            completed += 1
            session_store.set_node_progress(session_id, "gt_audit", completed, total_calls)
        return conv_id, verdicts

    # Run each judge over all conversations (concurrency bounded by the shared semaphore).
    runs_results = [
        await asyncio.gather(*[_judge_conversation(c, judge_llm) for c in conversations])
        for judge_llm in judge_llms
    ]
    conv_verdicts = _consensus_verdicts(runs_results, rule_ids)

    # ── Diff consensus verdicts against ground truth → flagged cases per rule ──────────
    pre_audit_cases = diff_cases(conv_verdicts, ground_truth_map, rule_ids)

    # ── Per-rule synthesis (keeps pivot text + optimizer discard-description feed) ──
    existing_pivot_asked = set(state.get("pivot_asked_rule_ids") or [])

    async def _synthesise(rule: dict) -> tuple[str, str]:
        rule_id = rule["rule_id"]
        cases = pre_audit_cases.get(rule_id, [])
        evaluable = sum(1 for g in ground_truth_map.values() if g.get(rule_id) in ("Yes", "No"))
        async with sem:
            findings = await _run_synthesis(rule_id, rule, cases, evaluable, len(conversations), llm)
        return rule_id, findings

    synth_results = await asyncio.gather(*[_synthesise(r) for r in rules])

    pre_audit_results: dict[str, str] = {}
    pivot_questions: list[ClarifyingQuestion] = []
    relabel_questions: list[ClarifyingQuestion] = []
    newly_pivot_asked: list[str] = []

    for rule_id, findings in synth_results:
        pre_audit_results[rule_id] = findings
        cases = pre_audit_cases.get(rule_id, [])
        gap = _extract_gap_type(findings)
        session_store.append_log(
            session_id, f"  GT audit: {rule_id} — {gap} ({len(cases)} case(s) flagged)"
        )

        display_name = rule_id.replace("__answer", "").replace("__trigger", "")

        if cases:
            relabel_questions.append(ClarifyingQuestion(
                question_id=str(uuid.uuid4()),
                parameter_name=rule_id,
                question_text=(
                    f"Ground-truth audit flagged {len(cases)} label(s) for '{display_name}' as "
                    f"inconsistent with the definition. Apply these corrections and score accuracy "
                    f"against the corrected ground truth?"
                ),
                rationale=(
                    "Per-conversation GT audit found labels that contradict the rule definition. "
                    "Accepting overlays the corrected labels (the source CSV is never changed)."
                ),
                question_type="gt_relabel",
                cases=cases,
                flagged_count=len(cases),
                metric_display_name=display_name,
            ))

        if "DESCRIPTION_MISMATCH" in findings and rule_id not in existing_pivot_asked:
            pivot_questions.append(ClarifyingQuestion(
                question_id=str(uuid.uuid4()),
                parameter_name=rule_id,
                question_text=_format_pivot_question(display_name, findings),
                rationale=(
                    "Pre-flight GT audit found DESCRIPTION_MISMATCH — description logic contradicts "
                    "ground truth before optimization begins."
                ),
                question_type="pivot",
            ))
            newly_pivot_asked.append(rule_id)

    total_flagged = sum(len(c) for c in pre_audit_cases.values())
    mismatch_count = sum(1 for f in pre_audit_results.values() if "DESCRIPTION_MISMATCH" in f)
    logger.info(
        "session=%s pre-flight GT audit: %d rule(s), %d label(s) flagged, %d mismatch(es)",
        session_id, len(pre_audit_results), total_flagged, mismatch_count,
    )

    return {
        "pre_audit_results": pre_audit_results,
        "pre_audit_cases": pre_audit_cases,
        # gt_relabel questions first so the actionable tables surface before pivot prompts
        "clarifying_questions": relabel_questions + pivot_questions,
        "pivot_asked_rule_ids": list(existing_pivot_asked | set(newly_pivot_asked)),
        "progress_log": [
            f"Pre-flight GT audit: {len(conversations)} conversation(s) checked, "
            f"{total_flagged} label(s) flagged across {sum(1 for c in pre_audit_cases.values() if c)} metric(s)"
        ],
    }


def _extract_gap_type(findings: str) -> str:
    for line in findings.split("\n"):
        stripped = line.strip()
        if stripped.startswith("Gap type:"):
            return stripped[len("Gap type:"):].strip()
    return "UNKNOWN"


def _extract_section(findings: str, prefix: str) -> str:
    for line in findings.split("\n"):
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()
    return ""


def _format_pivot_question(display_name: str, findings: str) -> str:
    desc_evaluates = _extract_section(findings, "What the description evaluates:")
    gt_rewards = _extract_section(findings, "What GT data rewards:")

    gaps_lines = []
    in_gaps = False
    for line in findings.split("\n"):
        stripped = line.strip()
        if stripped == "Alignment gaps:":
            in_gaps = True
            continue
        if in_gaps:
            if stripped == "" or stripped.startswith("Revised"):
                break
            if stripped.startswith("•"):
                gaps_lines.append(stripped)
    gap_text = "\n".join(gaps_lines) if gaps_lines else "• (none)"

    strategy_lines = []
    in_strategy = False
    for line in findings.split("\n"):
        stripped = line.strip()
        if stripped == "Revised optimization strategy:":
            in_strategy = True
            continue
        if in_strategy and stripped:
            strategy_lines.append(stripped)
            break
    strategy_text = strategy_lines[0] if strategy_lines else "(no strategy)"

    return (
        f"Pre-flight GT audit: DESCRIPTION_MISMATCH for '{display_name}'\n\n"
        f"Description evaluates:  {desc_evaluates}\n"
        f"GT actually rewards:    {gt_rewards}\n\n"
        f"Gap:\n{gap_text}\n\n"
        f"Suggested rewrite direction:\n{strategy_text}\n\n"
        f"Rewrite this description from scratch based on what your GT data actually rewards?\n"
        f"If yes, optimization starts with the correct logic from iteration 1."
    )


def _summarise_cases(cases: list[dict]) -> str:
    """Aggregate flagged cases into a compact, transcript-free evidence summary."""
    if not cases:
        return "No labels disagreed with the definition."
    directions: dict[str, int] = {}
    for c in cases:
        key = f"{c['current_gt']} → {c['should_be']}"
        directions[key] = directions.get(key, 0) + 1
    dir_text = "; ".join(f"{k}: {v}" for k, v in sorted(directions.items(), key=lambda kv: -kv[1]))
    sample_reasons = [f"• {c['reason']}" for c in cases[:6] if c.get("reason")]
    return f"Disagreement directions — {dir_text}\nRepresentative reasons:\n" + "\n".join(sample_reasons)


async def _run_synthesis(
    rule_id: str, rule: dict, cases: list[dict], evaluable: int, total_conversations: int, llm
) -> str:
    flagged = len(cases)
    fraction = (flagged / evaluable) if evaluable else 0.0
    prompt = (
        f"Rule ID: {rule_id}\n"
        f"Rule type: {rule.get('rule_type', 'answer')}\n\n"
        f"Description:\n{rule.get('description', '')}\n"
        + (f"\nTrigger definition:\n{rule.get('trigger_description')}\n" if rule.get("rule_type") == "dynamic" else "")
        + (
            f"\nAcross {total_conversations} conversations ({evaluable} with a Yes/No label), "
            f"the recorded ground truth disagreed with the definition on {flagged} conversation(s) "
            f"({fraction:.0%} of evaluable labels).\n\n"
            f"{_summarise_cases(cases)}\n\n"
        )
        + "Respond using this EXACT format — one short phrase or sentence per field:\n\n"
        "Gap type: <LABELLING_INCONSISTENCY | NO_GAP | DESCRIPTION_MISMATCH>\n\n"
        "What the description evaluates: <one short phrase, max 12 words>\n"
        "What GT data rewards: <one short phrase, max 12 words>\n\n"
        "Alignment gaps:\n"
        "• <one sentence max 25 words — or 'None.' if NO_GAP or LABELLING_INCONSISTENCY>\n\n"
        "Revised optimization strategy:\n"
        "<one sentence max 30 words — or 'No changes needed.' if NO_GAP or LABELLING_INCONSISTENCY>"
    )
    response = await llm.ainvoke([
        SystemMessage(content=_SYNTH_SYSTEM),
        HumanMessage(content=prompt),
    ])
    return response.content.strip()
