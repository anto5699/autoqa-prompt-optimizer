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
- After writing each criterion, apply this mental test: "Would this criterion produce the same verdict on a conversation I have not seen, if the same underlying behaviour is present?" If the answer depends on a specific phrase from the failure examples, reframe it in terms of the behaviour\
"""


_SYSTEM_V2 = """You are an expert QA rule description writer for contact centre quality evaluation.
Rule descriptions use the V2 Unified Criteria format evaluated by the Business Rule Adherence Analyst.

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

    for idx, rule_id in enumerate(below_target):
        record = records[rule_id]

        session_store.append_log(session_id, f"Optimising description for {rule_id} (iteration {iteration + 1})…")

        history_entry = {
            "iteration": iteration,
            "description": record["current_description"],
            "accuracy": record["current_accuracy"],
            "precision": record["current_precision"],
            "recall": record["current_recall"],
            "f1": record["current_f1"],
        }

        rule_answers = {qid: ans for qid, ans in user_answers.items() if qid_to_param.get(qid) == rule_id}

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
            new_trigger_description = await _optimise_description(trigger_record, rule_answers, llm, session_id)
            new_description = await _optimise_description(record, rule_answers, llm, session_id)
            records[rule_id] = {
                **record,
                "iteration_history": [*record["iteration_history"], history_entry],
                "current_description": new_description,
                "trigger_description": new_trigger_description,
                "current_predictions": {},
                "optimization_notes": f"Optimised at iteration {iteration + 1}",
            }
        else:
            # Single description optimisation: covers V1 static and all V2 records
            new_description = await _optimise_description(record, rule_answers, llm, session_id)
            records[rule_id] = {
                **record,
                "iteration_history": [*record["iteration_history"], history_entry],
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


def _is_stagnant(record: dict, min_entries: int = 3) -> bool:
    history = record.get("iteration_history", [])
    if len(history) < min_entries:
        return False
    recent = [h["accuracy"] for h in history[-min_entries:]]
    # Stagnant if improvement over last N iterations is less than 3 percentage points
    return (max(recent) - min(recent)) < 0.03


async def _optimise_description_v2(record: dict, user_answers: dict, llm, session_id: str) -> str:
    trajectory = _accuracy_trajectory(record)
    stagnant = _is_stagnant(record)

    if stagnant:
        rewrite_instruction = (
            "You MUST make a fundamentally different change — rewrite the CONDITION, EXPECTED BEHAVIOR, "
            "or EXCEPTION from a completely different angle. Do NOT make small edits to the current wording."
        )
    else:
        rewrite_instruction = (
            "Rewrite the description in V2 Unified Criteria format to address the identified failure patterns. "
            "Keep YES/NO/NA semantics intact — do not change CONDITION/EXCEPTION logic unless RCA explicitly requires it."
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

    prompt = (
        f"Rule ID: {record['rule_id']}\n"
        f"Speaker: {record['speaker']} | Evaluation type: {record['evaluation_type']}\n\n"
        f"Current description:\n{record['current_description']}\n\n"
        f"Root cause analysis:\n{record.get('rca_findings', 'Not available')}\n"
        f"{f'Accuracy trajectory: {trajectory}' if trajectory else ''}\n"
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
    record: dict, user_answers: dict, llm: BaseChatModel, session_id: str
) -> str:
    if record.get("version") == "v2":
        return await _optimise_description_v2(record, user_answers, llm, session_id)
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

    if _is_stagnant(record):
        rewrite_instruction = (
            "IMPORTANT: This rule has been STAGNANT — accuracy has not improved across multiple "
            "iterations. Incremental refinement is not working. You MUST make a fundamentally "
            "different change: reconsider whether PASS_CRITERIA are measuring the right observable "
            "signal, whether the ACTION statement should be reframed entirely, or whether the "
            "EXAMPLES are representative. Do NOT make small edits to the existing description — "
            "rewrite it from a different angle based on the error patterns."
        )
    else:
        rewrite_instruction = (
            "Rewrite the description in the structured format to address the identified failure patterns. "
            "Update PASS_CRITERIA to fix the specific errors identified in the RCA. "
            "Add or revise EXAMPLES to reflect the failure cases."
        )

    prompt = (
        f"Rule ID: {record['rule_id']}\n"
        f"Rule type: {rule_type} | Speaker: {record['speaker']} | "
        f"Evaluation type: {record['evaluation_type']} | n_messages: {record['n_messages']}\n\n"
        f"Current description:\n{record['current_description']}\n\n"
        f"Root cause analysis (use as evidence of failure patterns — write criteria that address the underlying behaviour, not the specific phrases or cases shown):\n{record.get('rca_findings', 'No findings available.')}\n\n"
        f"{trajectory_line}"
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
