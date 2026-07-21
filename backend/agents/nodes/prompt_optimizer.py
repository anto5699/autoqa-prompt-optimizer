import logging
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

from agents.state import OptimizationState
from config import get_llm, settings
from utils.session_store import session_store

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are an expert QA rule description writer for contact centre quality evaluation.
Rule descriptions are used by an LLM evaluation system to assess conversation transcripts.

You MUST output descriptions using this exact structured format:

METRIC_NAME: <2-5 word Title Case name>
SPEAKER: <Agent | Customer>
ACTION: <verb-first single sentence describing what is evaluated>
PASS_LOGIC: <ALL | ANY>
PASS_CRITERIA:
1. <atomic observable condition, detectable from transcript text>
2. <atomic observable condition>
EXAMPLES:
PASS:
1. "<example utterance that would pass>"
2. "<example utterance that would pass>"
FAIL:
1. "<example utterance that would fail>"
2. "<example utterance that would fail>"

Format rules:
- METRIC_NAME: 2-5 words, Title Case
- SPEAKER: must exactly match the rule's speaker field (Agent or Customer)
- ACTION: starts with a verb, one sentence only
- PASS_LOGIC: ALL if every criterion must be met; ANY if at least one is sufficient
- PASS_CRITERIA: 2-5 numbered conditions; each must be observable from transcript text alone
- EXAMPLES: minimum 2 PASS and 2 FAIL utterances that would appear verbatim in a transcript
- Never use vague terms: "appropriately", "effectively", "sufficiently", "properly", "well"
- Never require knowledge outside the transcript to evaluate a criterion
- Transcript is text-only: never infer tone, intonation, warmth, voice quality, or prosodic cues — every criterion must be derivable from the written words alone
- Adherence must be established from explicit verbal content in the transcript only — never from non-transcript actions (e.g., post-call system updates, CRM entries), implicit signals (e.g., agent hanging up), or behaviours that are not spoken in the conversation
- Evaluation is binary: the agent either adhered or did not. Never introduce partial adherence, scoring, thresholds, or weighted criteria
- Never add positional or time-bound constraints (e.g. "in the first 2 messages", "within N turns", "before the customer responds"). Message-window scoping is controlled by evaluation_type and n_messages, not the description
- Your entire response must not exceed 800 tokens. Be concise — use 2-3 PASS_CRITERIA and 2 PASS/FAIL EXAMPLES only if needed to stay within the limit

Generalisation rules:
- Write criteria that generalise to conversations not in this sample. Never anchor PASS_CRITERIA to a specific phrase, sentence, or pattern you observe in the failure examples
- The RCA failure examples are evidence of a failure pattern — write criteria that address the underlying observable behaviour, not the surface form of those specific transcripts
- EXAMPLES in your output must be representative illustrative utterances you compose yourself; do not copy or closely paraphrase verbatim transcript content from the failure examples
- After writing each criterion, apply this mental test: "Would this criterion produce the same verdict on a conversation I have not seen, if the same underlying behaviour is present?" If the answer depends on a specific phrase from the failure examples, reframe it in terms of the behaviour
- Do NOT add new PASS_CRITERIA that were absent from the original description unless the RCA explicitly identifies a gap in the original logic (i.e., the original description is structurally incapable of capturing the correct behaviour). Adding criteria to patch individual failure cases without a structural reason is overfitting.
- After writing your revised description, compare each new or changed criterion against the original description. If a criterion does not have a counterpart in the original and is not justified by an explicit RCA finding, remove it.\
"""


_SYSTEM_V2 = """You are an expert QA rule description writer for contact centre quality evaluation.
Rule descriptions use the V2 Unified Criteria format evaluated by the Conversation Quality Auditor.

You MUST output descriptions using this exact format, sections in this exact order:

CONDITION: <Always. | trigger event | AND/OR list>
EXPECTED BEHAVIOR:
  - <observable action from evaluated speaker>
  AND / OR / THEN
  - <next item>
PROHIBITED:
  - <disallowed action>
EXCEPTION: <None. | situation | list>

SECTION RULES:
- CONDITION: when the metric applies. "Always." for unconditional. Connectors: AND, OR. Any speaker.
- EXPECTED BEHAVIOR: mandatory. Observable actions from the evaluated speaker only. Connectors: AND, OR, THEN. Never reference the other speaker.
- PROHIBITED: optional — omit this section entirely if there are no prohibited actions. Implicit OR. Evaluated speaker only.
- EXCEPTION: mandatory. Use "None." when there are none. Implicit OR. Any participant or system event.

HARD CONSTRAINTS:
- Observable actions only — never use: "professional", "appropriately", "effectively", "well", "sufficiently", "adequately"
- Never reference internal tools, message identifiers, turn identifiers, or raw timestamps
- No conditional programming logic (if X then Y else Z) — split into separate metrics instead
- Never mix AND and OR within a single list (pick one connector per list)
- Present tense, active voice, plain English. All statements end with a period.
- Bullet ≤ 20 words; whole description ≤ 12 lines
- CONDITION, EXPECTED BEHAVIOR, and EXCEPTION are all mandatory
- PROHIBITED is optional; include only when a specific action must be explicitly forbidden
- Do NOT add CONDITION triggers, EXPECTED BEHAVIOR items, or EXCEPTIONS that were absent from the original description unless the RCA explicitly identifies that absence as a root cause of failures. Patching individual failure cases by tightening CONDITION or widening EXCEPTION is overfitting.

REFERENCE PATTERNS:
# Unconditional
CONDITION: Always.
EXPECTED BEHAVIOR:
  - Agent greets the customer.
EXCEPTION: No agent messages exist.

# Sequential
CONDITION: Customer requests account information.
EXPECTED BEHAVIOR:
  - Agent verifies identity.
  THEN
  - Agent provides information.
EXCEPTION:
  - Customer refuses verification.

# With PROHIBITED
CONDITION: Always.
EXPECTED BEHAVIOR:
  - Agent communicates courteously.
PROHIBITED:
  - Agent guarantees approval.
  - Agent shares customer data.
EXCEPTION: None.

ANTI-PATTERNS (never produce these):
- "Agent is professional." → write "Agent uses courteous language." (observable action)
- Mixing AND and OR: "Agent greets AND confirms name OR verifies ID" → pick one connector
- Branching: "If customer agrees, agent refunds; otherwise escalates." → split into two metrics
"""


async def prompt_optimizer(state: OptimizationState) -> dict:
    logger.info(
        "session=%s phase=optimizing_prompts iteration=%d",
        state["session_id"], state["current_iteration"],
    )

    session_id = state["session_id"]
    records = dict(state["parameter_records"])
    below_target = state["parameters_below_target"]
    user_answers = state.get("user_answers", {})
    qid_to_param = {q["question_id"]: q["parameter_name"] for q in state.get("clarifying_questions", [])}
    iteration = state["current_iteration"]

    session_store.update(session_id, {
        "current_phase": "optimizing_prompts",
        "progress_log": list(state.get("progress_log", [])),
    })

    completed_messages: list[str] = []

    try:
        llm_config = state.get("llm_config", {})
        llm = get_llm(
            model=llm_config.get("optimizer_model") or llm_config.get("model"),
            api_key=llm_config.get("optimizer_api_key") or llm_config.get("api_key"),
            base_url=llm_config.get("optimizer_base_url") or llm_config.get("base_url"),
            purpose="optimizer",
        )
        session_store.append_trace(session_id, {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "node": "prompt_optimizer", "model": llm.model_name, "event": "start",
            "details": {"iteration": iteration, "rules_below_target": len(below_target)},
        })
    except Exception as exc:
        session_store.append_log(session_id, f"ERROR: Could not initialise LLM — {exc}")
        logger.error("session=%s prompt_optimizer LLM init failed: %s", session_id, exc)
        return {
            "parameter_records": records,
            "current_iteration": iteration + 1,
            "current_phase": "error",
            "progress_log": [f"LLM initialisation failed: {exc}"],
        }

    total_rules = len(below_target)
    session_store.update(session_id, {"node_progress": {"node": "optimizing_prompts", "step": 0, "total": total_rules}})

    accuracy_target = state.get("accuracy_target", 0.90)
    pivot_approved_rules = set(state.get("pivot_approved_rules") or [])

    for idx, rule_id in enumerate(below_target):
        record = records[rule_id]

        session_store.append_log(session_id, f"Optimising description for {rule_id} (iteration {iteration + 1})…")

        rule_answers = {qid: ans for qid, ans in user_answers.items() if qid_to_param.get(qid) == rule_id}
        pivot_approved = rule_id in pivot_approved_rules

        is_dynamic_v1 = record.get("rule_type") == "dynamic" and record.get("version", "v1") == "v1"
        if is_dynamic_v1:
            # Optimize trigger and answer descriptions independently (V1 dynamic only)
            trigger_record = {
                **record,
                "rule_type": "trigger",
                "rule_id": f"{rule_id} (trigger)",
                "current_description": record.get("trigger_description") or "",
                "speaker": record.get("trigger_speaker") or "customer",
            }
            new_trigger_description = await _optimise_description(trigger_record, rule_answers, llm, session_id, pivot_approved=pivot_approved, accuracy_target=accuracy_target)
            new_description = await _optimise_description(record, rule_answers, llm, session_id, pivot_approved=pivot_approved, accuracy_target=accuracy_target)
            records[rule_id] = {
                **record,
                "current_description": new_description,
                "trigger_description": new_trigger_description,
                "current_predictions": {},
                "optimization_notes": f"Optimised at iteration {iteration + 1}",
            }
        else:
            # Single description optimisation: covers V1 static and all V2 records
            new_description = await _optimise_description(record, rule_answers, llm, session_id, pivot_approved=pivot_approved, accuracy_target=accuracy_target)
            records[rule_id] = {
                **record,
                "current_description": new_description,
                "current_predictions": {},
                "optimization_notes": f"Optimised at iteration {iteration + 1}",
            }
        msg = f"Description updated for {rule_id} (iteration {iteration + 1})"
        session_store.append_log(session_id, msg)
        completed_messages.append(msg)
        logger.info("session=%s rule_id=%s description updated for iteration %d", session_id, rule_id, iteration + 1)
        session_store.set_node_progress(session_id, "optimizing_prompts", idx + 1, total_rules)

    return {
        "parameter_records": records,
        "current_iteration": iteration + 1,
        "current_phase": "evaluating",
        "progress_log": completed_messages,
    }


def _accuracy_trajectory(record: dict) -> str:
    history = record.get("iteration_history", [])
    if not history:
        return ""
    # Deduplicate consecutive identical accuracies (benchmarking + optimizer both append entries)
    seen: list[float] = []
    for h in history:
        if not seen or h["accuracy"] != seen[-1]:
            seen.append(h["accuracy"])
    return "Accuracy trajectory: " + " → ".join(f"{a:.0%}" for a in seen)


def _is_high_accuracy(record: dict, threshold: float = 0.90) -> bool:
    history = record.get("iteration_history", [])
    if history:
        return history[-1]["accuracy"] >= threshold
    current = record.get("current_accuracy")
    return current is not None and current >= threshold


def _is_stagnant(record: dict, min_entries: int = 3) -> bool:
    history = record.get("iteration_history", [])
    if len(history) < min_entries:
        return False
    recent = [h["accuracy"] for h in history[-min_entries:]]
    # Stagnant if improvement over last N iterations is less than 3 percentage points
    return (max(recent) - min(recent)) < 0.03


def _is_regressing(record: dict) -> bool:
    history = record.get("iteration_history", [])
    if len(history) < 2:
        return False
    return history[-1]["accuracy"] < history[-2]["accuracy"]


async def _optimise_description_v2(record: dict, user_answers: dict, llm, session_id: str, *, pivot_approved: bool = False, accuracy_target: float = 0.90) -> str:
    trajectory = _accuracy_trajectory(record)
    stagnant = _is_stagnant(record)
    alignment_audit = record.get("alignment_audit")

    if pivot_approved and alignment_audit:
        rewrite_instruction = (
            "⚠ The user has approved discarding the current description logic. "
            "Write a completely fresh V2 Unified Criteria description based ONLY on the revised "
            "optimization strategy from the GT alignment audit below. Do not preserve any wording, "
            "CONDITION, or EXPECTED BEHAVIOR from the current description.\n\n"
            f"GT alignment audit:\n{alignment_audit}"
        )
        alignment_block = ""
    elif _is_high_accuracy(record):
        rewrite_instruction = (
            "IMPORTANT: This rule already achieves high accuracy (≥ 90%). "
            "Keep CONDITION, EXPECTED BEHAVIOR, PROHIBITED, and EXCEPTION text identical. "
            "The ONLY permitted change is a minimal wording refinement to a single section if the "
            "RCA identifies a specific edge case. "
            "If the RCA finds no actionable change, output the full description unchanged."
        )
        alignment_block = (
            f"Ground truth alignment audit (use to understand WHAT needs to change):\n{alignment_audit}\n\n"
            if alignment_audit else ""
        )
    elif _is_regressing(record):
        _h = record.get("iteration_history", [])
        rewrite_instruction = (
            f"⚠ REGRESSION: The last optimization attempt made accuracy worse "
            f"({_h[-2]['accuracy']:.0%} → {_h[-1]['accuracy']:.0%}). "
            "Make the MINIMUM targeted change needed to address the single clearest pattern in the RCA. "
            "Do NOT restructure CONDITION, EXPECTED BEHAVIOR, or EXCEPTION unless the RCA explicitly "
            "identifies that section as the root cause. "
            "If the RCA finding is uncertain, output the current description unchanged."
        )
        alignment_block = (
            f"Ground truth alignment audit (use to understand WHAT needs to change):\n{alignment_audit}\n\n"
            if alignment_audit else ""
        )
    elif stagnant:
        rewrite_instruction = (
            "You MUST make a fundamentally different change — rewrite the CONDITION, EXPECTED BEHAVIOR, "
            "or EXCEPTION from a completely different angle. Do NOT make small edits to the current wording."
        )
        alignment_block = (
            f"Ground truth alignment audit (use to understand WHAT needs to change):\n{alignment_audit}\n\n"
            if alignment_audit else ""
        )
    else:
        rewrite_instruction = (
            "Rewrite the description in V2 Unified Criteria format to address ALL identified failure patterns. "
            "For each failure type in the RCA, identify which section (CONDITION, EXPECTED BEHAVIOR, EXCEPTION) "
            "is responsible and change only that section. "
            "Keep YES/NO/NA semantics intact unless the RCA explicitly identifies the trigger logic as a root cause. "
            "If the RCA identifies both 'incorrectly marked as adhered' AND 'incorrectly marked as not adhered' failures, "
            "treat them as separate criteria problems: adjust EXPECTED BEHAVIOR for false passes "
            "and adjust CONDITION or EXCEPTION for false failures — do not collapse both into a single broad change."
        )
        alignment_block = (
            f"Ground truth alignment audit (use to understand WHAT needs to change):\n{alignment_audit}\n\n"
            if alignment_audit else ""
        )

    v2_constraints = (
        "HARD CONSTRAINTS:\n"
        "- Keep CONDITION, EXPECTED BEHAVIOR, EXCEPTION sections (all mandatory)\n"
        "- EXPECTED BEHAVIOR must refer only to the evaluated speaker\n"
        "- No positional constraints ('in first N messages', 'within N turns')\n"
        "- No message/turn identifiers or timestamps\n"
        "- No subjective language ('professional', 'appropriately', etc.)\n"
        "- No mixed AND/OR in one list\n"
        "- PROHIBITED section is optional — include only if a specific prohibition is warranted\n"
    )

    answers_block = ""
    if user_answers:
        answers_block = "\nUser clarifications:\n" + "\n".join(f"- {a}" for a in user_answers.values())

    original_desc = record.get("original_description") or ""
    original_block = (
        f"Original (baseline) description:\n{original_desc}\n\n"
        if original_desc and original_desc.strip() != record["current_description"].strip() else ""
    )

    accuracy_context = ""
    if record.get("initial_accuracy") is not None:
        accuracy_context = (
            f"Accuracy context: baseline {record['initial_accuracy']:.0%} → "
            f"current {record['current_accuracy']:.0%} → target {accuracy_target:.0%}\n\n"
        )

    rca_label = (
        "Root cause analysis — the RCA may identify MULTIPLE distinct failure types. "
        "You MUST address ALL of them in your revised description. "
        "Do not silently focus on one failure type and ignore others.\n"
        "Use findings as evidence of underlying behaviour patterns, not as a directive to copy specific transcript phrases:"
    )

    prompt = (
        f"Rule ID: {record['rule_id']}\n"
        f"Speaker: {record['speaker']} | Evaluation type: {record['evaluation_type']}\n\n"
        f"Current description:\n{record['current_description']}\n\n"
        f"{original_block}"
        f"{rca_label}\n{record.get('rca_findings', 'Not available')}\n\n"
        f"{f'Accuracy trajectory: {trajectory}' if trajectory else ''}\n"
        f"{accuracy_context}"
        f"{alignment_block}"
        f"{answers_block}\n\n"
        f"{v2_constraints}\n"
        f"{rewrite_instruction}\n\n"
        "Output ONLY the improved V2 Unified Criteria description. No explanation, no preamble."
    )

    try:
        response = await llm.ainvoke([
            SystemMessage(content=_SYSTEM_V2),
            HumanMessage(content=prompt),
        ])
        return (response.content or "").strip() or record["current_description"]
    except Exception:
        return record["current_description"]


async def _optimise_description(
    record: dict, user_answers: dict, llm: BaseChatModel, session_id: str, *, pivot_approved: bool = False, accuracy_target: float = 0.90
) -> str:
    if record.get("version") == "v2":
        return await _optimise_description_v2(record, user_answers, llm, session_id, pivot_approved=pivot_approved, accuracy_target=accuracy_target)
    # V1 path continues unchanged below
    rule_type = record["rule_type"]
    clarifications = "\n".join(f"- {v}" for v in user_answers.values()) if user_answers else "None"

    if rule_type == "trigger":
        constraints = (
            "The PASS_CRITERIA must remain detectable from transcript text. "
            "Do not change evaluation_type, n_messages, or speaker."
        )
    else:
        constraints = (
            "The PASS_CRITERIA must be evaluable solely from transcript evidence. "
            "Do not change evaluation_type, n_messages, or speaker. "
            "Do NOT include any language about inapplicability, the trigger condition being absent, "
            "or 'when the scenario does not apply'. The trigger rule already handles Not Applicable "
            "automatically — the description must only specify what constitutes adherence when the "
            "scenario IS in scope."
        )

    trajectory = _accuracy_trajectory(record)
    trajectory_line = f"Accuracy history: {trajectory}\n\n" if trajectory else ""

    if _is_high_accuracy(record):
        rewrite_instruction = (
            "IMPORTANT: This rule already achieves high accuracy (≥ 90%). The PASS_CRITERIA "
            "text must remain WORD-FOR-WORD IDENTICAL to the current description — do not "
            "rephrase, reorder, or modify any criterion. The ONLY permitted change is to add "
            "or revise EXAMPLES to illustrate the one edge case identified in the RCA. If the "
            "RCA finds no actionable change, output the full description unchanged in the "
            "structured format."
        )
    elif _is_regressing(record):
        _h = record.get("iteration_history", [])
        rewrite_instruction = (
            f"⚠ REGRESSION: The last optimization attempt made accuracy worse "
            f"({_h[-2]['accuracy']:.0%} → {_h[-1]['accuracy']:.0%}). "
            "Make the MINIMUM targeted change needed to address the single clearest pattern in the RCA. "
            "Do NOT restructure, reorder, or rephrase PASS_CRITERIA that were not directly identified "
            "as failure causes. Do NOT change PASS_LOGIC unless the RCA explicitly identifies it as the root cause. "
            "If the RCA finding is uncertain, output the current description unchanged."
        )
    elif _is_stagnant(record):
        rewrite_instruction = (
            "IMPORTANT: This rule has been STAGNANT — accuracy has not improved across multiple "
            "iterations. Incremental refinement is not working. You MUST make a fundamentally "
            "different structural change. "
            "PROHIBITED: Switching PASS_LOGIC (ALL↔ANY) while keeping the same PASS_CRITERIA "
            "items is NOT a structural change — do not do this alone, even if the RCA recommends it. "
            "REQUIRED: Your output MUST differ from the current description in at least one "
            "PASS_CRITERION item (the criterion text itself, not just the PASS_LOGIC value). "
            "Choose at least one of: (a) replace individual criteria with ones that capture the "
            "underlying behaviour rather than surface phrasing, (b) combine all criteria into a "
            "single PASS_CRITERION that handles the full range of valid behaviours including "
            "implicit and combined signals (reduce PASS_CRITERIA to one item), "
            "(c) rewrite the ACTION verb to reframe what is being measured entirely. "
            "Do NOT make small edits to existing criterion text — rewrite from a different angle."
        )
    else:
        rewrite_instruction = (
            "Rewrite the description in the structured format to address ALL identified failure patterns. "
            "For each failure type in the RCA:\n"
            "  • Identify the specific PASS_CRITERION (or absence of one) responsible for that failure type.\n"
            "  • Change ONLY that criterion — do not globally tighten or loosen unrelated criteria.\n"
            "If the RCA identifies both 'incorrectly marked as adhered' AND 'incorrectly marked as not adhered' failures, "
            "these are not necessarily contradictory — they likely point to DIFFERENT criteria. "
            "Tighten the criterion that causes false passes; loosen the criterion that causes false failures. "
            "If a single criterion is responsible for both, prioritise reducing the more frequent failure type "
            "and add a qualifier (e.g., PASS_LOGIC change or an EXCEPTION note) for the less frequent one."
        )

    alignment_audit = record.get("alignment_audit")
    if pivot_approved and alignment_audit:
        alignment_block = (
            "⚠ The user has approved discarding the current description logic. "
            "Write a completely fresh description based ONLY on the revised optimization "
            "strategy from the GT alignment audit below. Do not preserve any wording or "
            "criteria from the current description.\n\n"
            f"GT alignment audit:\n{alignment_audit}\n\n"
        )
    elif alignment_audit:
        alignment_block = (
            f"Ground truth alignment audit (systemic gaps between the description logic and what "
            f"ground truth actually rewards — use this to understand WHAT needs to change, not just HOW):\n"
            f"{alignment_audit}\n\n"
        )
    else:
        alignment_block = ""

    original_desc = record.get("original_description") or ""
    original_block = (
        f"Original (baseline) description:\n{original_desc}\n\n"
        if original_desc and original_desc.strip() != record["current_description"].strip() else ""
    )

    accuracy_context = ""
    if record.get("initial_accuracy") is not None:
        accuracy_context = (
            f"Accuracy context: baseline {record['initial_accuracy']:.0%} → "
            f"current {record['current_accuracy']:.0%} → target {accuracy_target:.0%}\n\n"
        )

    rca_label = (
        "Root cause analysis — the RCA may identify MULTIPLE distinct failure types. "
        "You MUST address ALL of them in your revised description. "
        "Do not silently focus on one failure type and ignore others.\n"
        "Use findings as evidence of underlying behaviour patterns, not as a directive to copy specific transcript phrases:"
    )

    prompt = (
        f"Rule ID: {record['rule_id']}\n"
        f"Rule type: {rule_type} | Speaker: {record['speaker']} | "
        f"Evaluation type: {record['evaluation_type']} | n_messages: {record['n_messages']}\n\n"
        f"Current description:\n{record['current_description']}\n\n"
        f"{original_block}"
        f"{rca_label}\n{record.get('rca_findings', 'No findings available.')}\n\n"
        f"{alignment_block}"
        f"{trajectory_line}"
        f"{accuracy_context}"
        f"User clarifications:\n{clarifications}\n\n"
        f"Constraints: {constraints}\n\n"
        f"{rewrite_instruction} "
        "Respond with only the structured description, no preamble."
    )

    response = await llm.ainvoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=prompt),
    ])
    return response.content.strip()
