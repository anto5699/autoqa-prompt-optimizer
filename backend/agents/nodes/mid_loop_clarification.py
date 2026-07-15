from __future__ import annotations

import json
import logging
import uuid

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from agents.state import ClarifyingQuestion, OptimizationState
from config import get_llm, settings
from utils.session_store import session_store

logger = logging.getLogger(__name__)

_MAX_QUESTIONS = 5

_SYSTEM = (
    "You are an expert QA analyst. Given a root cause analysis of LLM evaluation errors for a QA rule, "
    "determine if the errors stem from genuine ambiguity in the rule description that a domain expert "
    "could resolve with a targeted clarifying question. Only flag real ambiguity that user input can fix "
    "— not errors caused by LLM capability limits or inherently unpredictable transcript variation.\n\n"
    "IMPORTANT: Never ask about rule metadata fields (evaluation_type, n_messages, speaker, rule_type, rule_id). "
    "These are fixed system parameters defined in the evaluation engine system prompt — their semantics are "
    "already resolved. Only ask about domain-specific ambiguities in the description text itself.\n"
    "Never ask about partial vs full adherence — evaluation is strictly binary (adhered or not adhered).\n"
    "Never ask about or suggest time-bound or positional constraints (e.g. 'first N messages', 'within N turns') "
    "— message-window scoping is controlled by evaluation_type and n_messages, not the description.\n"
    "Never ask about tone, intonation, warmth, voice quality, or prosodic cues — the transcript is text-only "
    "and evaluation must be derivable from the written words alone.\n"
    "Never ask whether non-transcript actions (e.g., post-call system updates, CRM entries, agent hanging up) "
    "or implicit signals can satisfy a criterion — adherence must be established from explicit verbal content "
    "in the transcript only.\n"
    "AUDIENCE RULE: Write every question in plain, everyday language that a non-technical call centre "
    "QA manager or supervisor can understand and answer without any knowledge of the evaluation system. "
    "Never reference internal system concepts such as 'PASS criterion', 'PASS_CRITERIA', 'description', "
    "'evaluation criteria', 'the rule', or 'this criterion'. Never use ML or QA-system jargon. "
    "Ask about real-world observable behaviour only — frame as scope or boundary questions, for example: "
    "'When an agent says X, does that count as Y?', 'Is Z enough to satisfy this?', "
    "'If the agent only does A but not B, should that pass or fail?'. "
    "Keep questions to 1–2 sentences."
)


def _is_stagnant(record: dict) -> bool:
    window = settings.stagnation_window
    history = record.get("iteration_history", [])
    if len(history) < window:
        return False
    recent = [h["accuracy"] for h in history[-window:]]
    return (max(recent) - min(recent)) < settings.stagnation_spread


def _accuracy_trajectory(record: dict) -> str:
    history = record.get("iteration_history", [])
    if not history:
        return ""
    seen: list[float] = []
    for h in history:
        if not seen or h["accuracy"] != seen[-1]:
            seen.append(h["accuracy"])
    return " → ".join(f"{a:.0%}" for a in seen)


async def mid_loop_clarification(state: OptimizationState) -> dict:
    session_id = state["session_id"]
    below_target = state["parameters_below_target"]
    clarified = set(state.get("clarified_rule_ids", []))
    records = state["parameter_records"]
    existing_answers = state.get("user_answers", {})
    iteration = state.get("current_iteration", 0)
    max_iterations = state.get("max_iterations", 8)

    candidates = [r for r in below_target if r not in clarified]
    if not candidates:
        return {}

    llm_config = state.get("llm_config", {})
    llm = get_llm(
        model=llm_config.get("optimizer_model") or llm_config.get("model"),
        api_key=llm_config.get("optimizer_api_key") or llm_config.get("api_key"),
        base_url=llm_config.get("optimizer_base_url") or llm_config.get("base_url"),
        purpose="optimizer",
    )

    questions: list[ClarifyingQuestion] = []
    newly_clarified: list[str] = []

    for rule_id in candidates:
        if len(questions) >= _MAX_QUESTIONS:
            break
        record = records.get(rule_id, {})
        if not _is_stagnant(record):
            continue
        rca_findings = record.get("rca_findings", "")
        prior_questions = [
            q for q in state.get("clarifying_questions", [])
            if q["parameter_name"] == rule_id
        ]
        question = None
        if rca_findings and not rca_findings.startswith("RCA unavailable"):
            question = await _maybe_generate_question(
                rule_id, record, rca_findings, iteration, max_iterations, session_id,
                state["system_prompt"], llm,
                system_prompt_v2=state.get("system_prompt_v2", ""),
                prior_questions=prior_questions,
                prior_answers=existing_answers,
            )
        if not question:
            # Fallback: rule is stagnant but the LLM found no specific ambiguity to resolve
            # (or RCA findings were unavailable). Force an open question so a human can break
            # the deadlock — incremental LLM rewrites have not been enough.
            current_acc = record.get("current_accuracy", 0)
            history_len = len(record.get("iteration_history", []))
            question = ClarifyingQuestion(
                question_id=str(uuid.uuid4()),
                parameter_name=rule_id,
                question_text=(
                    f"This metric has been stuck around {current_acc:.0%} accuracy for "
                    f"{history_len} iteration(s) despite multiple rewrites. "
                    f"Can you describe a borderline situation — something your team regularly "
                    f"debates — where it might not be obvious whether an agent should pass or "
                    f"fail this check?"
                ),
                rationale="Forced fallback: rule remains stagnant; no specific ambiguity identified by LLM.",
                clarification_forced=True,
            )
        questions.append(question)
        newly_clarified.append(rule_id)

    # --- Pivot questions: ask user to approve replacing description logic for DESCRIPTION_MISMATCH ---
    pivot_asked = set(state.get("pivot_asked_rule_ids", []))
    newly_pivot_asked: list[str] = []
    existing_approved = set(state.get("pivot_approved_rules", []))

    for rule_id in below_target:
        if rule_id in pivot_asked:
            continue
        record = records.get(rule_id, {})
        audit = record.get("alignment_audit", "") or ""
        if "DESCRIPTION_MISMATCH" not in audit:
            continue
        display_name = rule_id.replace("__answer", "").replace("__trigger", "")
        pivot_q = ClarifyingQuestion(
            question_id=str(uuid.uuid4()),
            parameter_name=rule_id,
            question_text=(
                f"For '{display_name}', the GT alignment audit found a description logic mismatch:\n\n"
                f"{audit}\n\n"
                f"Would you like to discard the current description and rewrite it from scratch "
                f"based on the revised optimization strategy above?"
            ),
            rationale="GT alignment audit found DESCRIPTION_MISMATCH — description logic contradicts ground truth.",
            question_type="pivot",
        )
        questions.append(pivot_q)
        newly_pivot_asked.append(rule_id)

    if not questions:
        return {}

    # Write to session_store before interrupt — LangGraph state won't reflect the interrupt value.
    session_store.update(session_id, {
        "current_phase": "awaiting_clarification",
        "clarifying_questions": list(questions),
    })
    logger.info(
        "session=%s mid_loop_clarification: %d question(s) for %s — pausing",
        session_id, len(questions), newly_clarified,
    )

    resume_data = interrupt({"clarifying_questions": questions})

    new_answers = resume_data.get("user_answers", {}) if isinstance(resume_data, dict) else {}
    merged_answers = {**existing_answers, **new_answers}

    newly_approved: list[str] = []
    for q in questions:
        if q.get("question_type") == "pivot":
            answer = new_answers.get(q["question_id"], "").strip().lower()
            if answer.startswith("y"):
                newly_approved.append(q["parameter_name"])

    return {
        "user_answers": merged_answers,
        "clarifying_questions": questions,
        "clarification_complete": True,
        "clarified_rule_ids": list(clarified | set(newly_clarified)),
        "pivot_asked_rule_ids": list(pivot_asked | set(newly_pivot_asked)),
        "pivot_approved_rules": list(existing_approved | set(newly_approved)),
        "current_phase": "optimizing_prompts",
    }


async def _maybe_generate_question(
    rule_id: str,
    record: dict,
    rca_findings: str,
    iteration: int,
    max_iterations: int,
    session_id: str,
    system_prompt: str,
    llm,
    *,
    system_prompt_v2: str = "",
    prior_questions: list | None = None,
    prior_answers: dict | None = None,
) -> ClarifyingQuestion | None:
    active_system_prompt = system_prompt_v2 if record.get("version") == "v2" else system_prompt
    trajectory = _accuracy_trajectory(record)
    stagnancy_note = (
        f"  (stagnant — {_STAGNANT_MIN_ENTRIES}+ identical iterations)"
        if _is_stagnant(record) else ""
    )
    trajectory_line = f"Accuracy trajectory: {trajectory}{stagnancy_note}\n" if trajectory else ""

    best_acc = record.get("best_accuracy")
    initial_acc = record.get("initial_accuracy")
    current_acc = record.get("current_accuracy")
    perf_line = ""
    if best_acc is not None and initial_acc is not None:
        perf_line = (
            f"Starting accuracy: {initial_acc:.0%}  |  "
            f"Best reached: {best_acc:.0%}  |  "
            f"Current: {current_acc:.0%}\n"
        )

    prior_qa_block = ""
    if prior_questions and prior_answers:
        pairs = []
        for q in prior_questions:
            answer = prior_answers.get(q["question_id"], "").strip()
            if answer:
                pairs.append(f"  Q: {q['question_text']}\n  A: {answer}")
        if pairs:
            prior_qa_block = (
                "Previously answered clarifications for this rule:\n"
                + "\n".join(pairs)
                + "\n\nIMPORTANT: Do NOT ask about any dimension already addressed by the answers above. "
                "Your question must probe a different, unresolved aspect of the description.\n\n"
            )

    trigger_block = ""
    if record.get("rule_type") == "dynamic" and record.get("trigger_description"):
        trigger_block = (
            f"Trigger description (determines when this metric is in scope):\n"
            f"{record.get('trigger_description', '')}\n\n"
        )

    prompt = (
        f"Evaluation engine system prompt (defines how evaluation_type, n_messages, speaker are used):\n"
        f"{active_system_prompt}\n\n"
        f"---\n"
        f"Rule ID: {rule_id}\n"
        f"Rule type: {record.get('rule_type')} | Speaker: {record.get('speaker')}\n"
        f"Iteration: {iteration} of {max_iterations}\n\n"
        f"{trajectory_line}"
        f"{perf_line}"
        f"\nCurrent description (answer — evaluates agent adherence):\n{record.get('current_description', '')}\n\n"
        f"{trigger_block}"
        f"{prior_qa_block}"
        f"Root cause analysis:\n{rca_findings}\n\n"
        "This rule has been stagnant — accuracy has not improved despite multiple optimisation attempts. "
        "Does the RCA indicate that the root cause is genuine ambiguity that a domain expert's answer could resolve?\n"
        "Respond with a JSON object only:\n"
        '{"needs_clarification": true/false, "question_text": "...", "rationale": "..."}\n'
        "Rules for question_text:\n"
        "- Must be a complete interrogative sentence ending with '?' — not a directive, not a statement.\n"
        "- Must target the specific unresolved boundary from the RCA. "
        "Example: 'When the customer says nothing after the agent proposes a transfer, does that count as consent?'\n"
        "- Do not include the words 'PASS_CRITERIA', 'description', 'criterion', or any system prompt terminology.\n"
        "- Do not restate criteria already explicit in the description.\n"
        "Set needs_clarification to false if the ambiguity cannot be resolved by a domain expert answer "
        "(e.g. it is caused by LLM capability limits or inherent transcript variation). "
        "Do NOT ask about evaluation_type, n_messages, speaker, rule_type, or rule_id. "
        "If needs_clarification is false, question_text can be empty."
    )

    try:
        response = await llm.ainvoke([
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=prompt),
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("session=%s rule_id=%s mid-loop ambiguity check failed: %s", session_id, rule_id, exc)
        return None

    if not isinstance(data, dict) or not data.get("needs_clarification"):
        return None
    question_text = str(data.get("question_text", "")).strip()
    if not question_text:
        return None

    return ClarifyingQuestion(
        question_id=str(uuid.uuid4()),
        parameter_name=rule_id,
        question_text=question_text,
        rationale=str(data.get("rationale", "")),
    )
