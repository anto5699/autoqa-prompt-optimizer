import json
import logging
import uuid
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from agents.state import ClarifyingQuestion, OptimizationState
from config import get_llm
from utils.session_store import session_store

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are an expert QA rule analyst. Your job is to identify ambiguities in QA rule descriptions "
    "that would make them difficult for an LLM to evaluate consistently from transcript text alone. "
    "Be specific and concise. Only flag genuine ambiguities — do not invent issues.\n\n"
    "IMPORTANT: Never ask about rule metadata fields (evaluation_type, n_messages, speaker, rule_type, rule_id). "
    "These are fixed system parameters handled by the evaluation engine — their semantics are defined in the "
    "system prompt provided to you. Only ask about domain-specific ambiguities in the description text itself.\n"
    "Never ask about partial vs full adherence — evaluation is strictly binary (adhered or not adhered).\n"
    "Never ask about or suggest time-bound or positional constraints (e.g. 'first N messages', 'within N turns') "
    "— message-window scoping is controlled by evaluation_type and n_messages, not the description.\n"
    "Never ask about tone, intonation, warmth, voice quality, or prosodic cues — the transcript is text-only "
    "and evaluation must be derivable from the written words alone. Descriptions requiring tonal inference are "
    "not ambiguous; they are out-of-scope and must be rewritten to use text-observable criteria only.\n"
    "Never ask whether non-transcript actions (e.g., post-call system updates, CRM entries, agent hanging up) "
    "or implicit signals can satisfy a criterion — adherence must be established from explicit verbal content "
    "in the transcript only.\n"
    "UNIQUENESS RULE: When generating multiple questions for the same rule, each question MUST probe a "
    "distinct ambiguity dimension. Never generate two questions that address the same underlying ambiguity "
    "from slightly different angles. Each question must unlock different information — for example, one "
    "about what specific language or behaviour constitutes adherence (PASS criteria), and a second about "
    "what distinguishes edge cases or borderline behaviours that could be read either way. If only one "
    "genuine ambiguity exists, return a single question rather than padding with an overlapping one.\n"
    "Never ask 'should the description include...', 'should the description mention...', 'should the description cover...', "
    "'should the description explicitly...', or 'should the rule description include/mention/cover/specify...'. "
    "These are description-writing choices, not domain clarifications. Frame every question as a scope or boundary "
    "question about real-world conditions — for example: 'does X count as Y?', 'is Z sufficient to satisfy this?', "
    "'what is the minimum requirement for W?', 'does A qualify as B even when C is absent?'.\n"
    "For answer rules that are part of a trigger/answer pair: never ask about scenarios where the trigger condition "
    "is absent, not applicable, or has not fired. When the trigger rule does not fire, the evaluation engine "
    "automatically marks the answer rule Not Applicable — the answer description has nothing to handle for that case. "
    "Ask only about what the agent must do when the scenario IS in scope.\n"
    "AUDIENCE RULE: Write every question in plain, everyday language that a non-technical call centre "
    "QA manager or supervisor can understand and answer without any knowledge of the evaluation system. "
    "Never reference internal system concepts such as 'PASS criterion', 'PASS_CRITERIA', 'description', "
    "'evaluation criteria', 'the rule', or 'this criterion'. Never use ML or QA-system jargon. "
    "Ask about real-world observable behaviour only — frame as scope or boundary questions, for example: "
    "'When an agent says X, does that count as Y?', 'Is Z enough to satisfy this?', "
    "'If the agent only does A but not B, should that pass or fail?'. "
    "Keep questions to 1–2 sentences."
)

_MAX_QUESTIONS_PER_RULE = 2
_MAX_TOTAL_QUESTIONS = 10


async def ambiguity_detection(state: OptimizationState) -> dict:
    logger.info("session=%s phase=detecting_ambiguity", state["session_id"])
    session_store.update(state["session_id"], {"current_phase": "detecting_ambiguity"})

    llm_config = state.get("llm_config", {})
    llm = get_llm(
        model=llm_config.get("optimizer_model") or llm_config.get("model"),
        api_key=llm_config.get("optimizer_api_key") or llm_config.get("api_key"),
        base_url=llm_config.get("optimizer_base_url") or llm_config.get("base_url"),
        purpose="optimizer",
    )
    session_store.append_trace(state["session_id"], {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "node": "ambiguity_detection", "model": llm.model_name, "event": "start",
        "details": {"rules": len(state["rules"])},
    })

    # Include pivot questions from pre_flight_gt_audit (if any)
    all_questions: list[ClarifyingQuestion] = list(state.get("clarifying_questions") or [])

    system_prompt = state["system_prompt"]
    system_prompt_v2 = state.get("system_prompt_v2", "")

    for rule in state["rules"]:
        if len(all_questions) >= _MAX_TOTAL_QUESTIONS:
            break

        active_system_prompt = system_prompt_v2 if rule.get("version") == "v2" else system_prompt

        if rule["rule_type"] == "dynamic":
            trigger_rule = {**rule, "rule_type": "trigger", "description": rule.get("trigger_description", "")}
            trigger_qs = await _analyse_rule(trigger_rule, active_system_prompt, llm)
            remaining = _MAX_TOTAL_QUESTIONS - len(all_questions)
            all_questions.extend(trigger_qs[:min(1, remaining)])

            if len(all_questions) < _MAX_TOTAL_QUESTIONS:
                answer_qs = await _analyse_rule(rule, active_system_prompt, llm)
                remaining = _MAX_TOTAL_QUESTIONS - len(all_questions)
                all_questions.extend(answer_qs[:min(1, remaining)])
        else:
            questions = await _analyse_rule(rule, active_system_prompt, llm)
            remaining = _MAX_TOTAL_QUESTIONS - len(all_questions)
            all_questions.extend(questions[:min(_MAX_QUESTIONS_PER_RULE, remaining)])

    if all_questions:
        logger.info(
            "session=%s ambiguity_detection: %d questions generated, pausing for user",
            state["session_id"], len(all_questions),
        )
        # Write to session_store BEFORE interrupt() — LangGraph state.values won't reflect
        # the interrupt value, so get_session reads it from here instead.
        session_store.update(state["session_id"], {
            "current_phase": "awaiting_clarification",
            "clarifying_questions": list(all_questions),
        })
        resume_data = interrupt({"clarifying_questions": all_questions})
        user_answers = resume_data.get("user_answers", {}) if isinstance(resume_data, dict) else {}

        newly_approved = [
            q["parameter_name"]
            for q in all_questions
            if q.get("question_type") == "pivot"
            and user_answers.get(q["question_id"], "").strip().lower().startswith("y")
        ]

        gt_update = _apply_gt_relabels(state, all_questions, user_answers)

        return {
            "clarifying_questions": all_questions,
            "clarification_complete": True,
            "user_answers": user_answers,
            "pivot_approved_rules": list(set(state.get("pivot_approved_rules") or []) | set(newly_approved)),
            "current_phase": "generating_baselines",
            "progress_log": [
                f"Ambiguity detection: {len(all_questions)} clarifying question(s) generated — answers received"
            ] + gt_update.pop("progress_log", []),
            **gt_update,
        }

    return {
        "clarifying_questions": all_questions,
        "clarification_complete": True,
        "current_phase": "generating_baselines",
        "progress_log": [
            "Ambiguity detection: no ambiguities found — proceeding"
        ],
    }


def _apply_gt_relabels(
    state: OptimizationState,
    all_questions: list[ClarifyingQuestion],
    user_answers: dict,
) -> dict:
    """Overlay accepted GT-audit relabels onto the ground-truth map, non-destructively.

    Returns a partial state update: a corrected `ground_truth_map`, a one-time snapshot of the
    original under `ground_truth_map_original`, and `gt_corrections_applied` per rule. Returns {}
    when nothing was accepted. The source CSV is never touched.
    """
    accepted = [
        q for q in all_questions
        if q.get("question_type") == "gt_relabel"
        and user_answers.get(q["question_id"], "").strip().lower().startswith("y")
    ]
    if not accepted:
        return {}

    original = state["ground_truth_map"]
    corrected = {conv_id: dict(labels) for conv_id, labels in original.items()}
    corrections: dict[str, list[dict]] = {}
    applied_total = 0

    for q in accepted:
        rule_id = q["parameter_name"]
        rule_corrections: list[dict] = []
        for case in q.get("cases", []):
            conv_id = case["conversation_id"]
            should_be = case["should_be"]
            if conv_id not in corrected:
                continue
            from_gt = corrected[conv_id].get(rule_id)
            if from_gt == should_be:
                continue
            corrected[conv_id][rule_id] = should_be
            rule_corrections.append({
                "conversation_id": conv_id,
                "from_gt": from_gt,
                "to_gt": should_be,
            })
        if rule_corrections:
            corrections[rule_id] = rule_corrections
            applied_total += len(rule_corrections)

    if not applied_total:
        return {}

    existing = state.get("gt_corrections_applied") or {}
    merged = {**existing, **corrections}

    return {
        "ground_truth_map": corrected,
        # Snapshot the pre-correction map once; keep the earliest snapshot on repeat passes.
        "ground_truth_map_original": state.get("ground_truth_map_original") or original,
        "gt_corrections_applied": merged,
        "progress_log": [
            f"GT audit: applied {applied_total} label correction(s) across "
            f"{len(corrections)} metric(s) — accuracy will be scored against corrected ground truth"
        ],
    }


async def _analyse_rule(rule: dict, system_prompt: str, llm) -> list[ClarifyingQuestion]:
    rule_type = rule["rule_type"]
    description = rule["description"]

    if rule_type == "trigger":
        guidance = (
            "Analyse this TRIGGER rule description for ambiguities that could cause inconsistent detection:\n"
            "- Is the trigger condition specific enough to detect from transcript text?\n"
            "- Does it require exact phrasing or allow semantic equivalents?\n"
            "- Could partial matches count (agent-initiated vs customer-requested)?\n"
            "- Is it unclear what observable evidence in the transcript would confirm or deny the trigger?"
        )
    else:
        guidance = (
            "Analyse this ANSWER rule description for ambiguities that could cause inconsistent evaluation. "
            "Identify up to 2 DISTINCT ambiguity dimensions from the following non-overlapping categories:\n"
            "  PASS_CRITERIA: vague or subjective language that makes it unclear what specific words or "
            "actions the agent must produce (e.g. 'appropriately', 'professionally', 'effectively')\n"
            "  EDGE_CASES: plausible agent behaviours that could reasonably be read as either adherent or "
            "non-adherent (borderline cases the description does not resolve)\n"
            "  EVIDENCE: whether the criterion can be observed from transcript text alone, or requires "
            "external knowledge or inference beyond what is written\n"
            "Only ask about dimensions where genuine ambiguity exists. Each question must target a "
            "different category — never two questions from the same category."
        )

    prompt = (
        f"Evaluation engine system prompt (defines how evaluation_type, n_messages, speaker are used):\n"
        f"{system_prompt}\n\n"
        f"---\n"
        f"Rule ID: {rule['rule_id']}\n"
        f"Rule type: {rule_type} | Speaker: {rule['speaker']} | "
        f"Evaluation type: {rule['evaluation_type']} | n_messages: {rule['n_messages']}\n"
        f"Description: {description}\n\n"
        f"{guidance}\n\n"
        "Return a JSON array of objects, each with keys:\n"
        "  question_text (string): the clarifying question about the DESCRIPTION only\n"
        "  rationale (string): why this ambiguity matters for LLM evaluation\n"
        "  dimension (string): which category this question targets — one of PASS_CRITERIA, EDGE_CASES, EVIDENCE\n\n"
        "Return at most 2 questions. If you return 2, they MUST target different dimension values — "
        "never two questions with the same dimension. Prefer 1 precise question over 2 overlapping ones. "
        "If the description is clear and unambiguous, return [].\n"
        "Do NOT ask about evaluation_type, n_messages, speaker, rule_type, or rule_id — these are explained "
        "in the system prompt above and are not user-configurable.\n"
        "Return ONLY the JSON array, no preamble."
    )

    response = await llm.ainvoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=prompt),
    ])
    raw = response.content.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    items = json.loads(raw)
    if not isinstance(items, list):
        raise ValueError(
            f"Ambiguity detection for rule '{rule['rule_id']}' returned unexpected format: {raw[:200]}"
        )

    questions: list[ClarifyingQuestion] = []
    for item in items[:_MAX_QUESTIONS_PER_RULE]:
        if isinstance(item, dict) and "question_text" in item:
            questions.append(ClarifyingQuestion(
                question_id=str(uuid.uuid4()),
                parameter_name=rule["rule_id"],
                question_text=str(item["question_text"]),
                rationale=str(item.get("rationale", "")),
            ))

    return questions
