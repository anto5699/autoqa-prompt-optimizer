import json
import logging
import uuid

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from agents.state import ClarifyingQuestion, OptimizationState
from config import get_llm
from utils.session_store import session_store

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are an expert QA rule analyst. Your job is to identify ambiguities in QA rule descriptions "
    "that would make them difficult for an LLM to evaluate consistently from transcript text alone. "
    "Be specific and concise. Only flag genuine ambiguities — do not invent issues."
)

_MAX_QUESTIONS_PER_RULE = 2
_MAX_TOTAL_QUESTIONS = 10


async def ambiguity_detection(state: OptimizationState) -> dict:
    logger.info("session=%s phase=detecting_ambiguity", state["session_id"])
    session_store.update(state["session_id"], {"current_phase": "detecting_ambiguity"})

    all_questions: list[ClarifyingQuestion] = []

    for rule in state["rules"]:
        if len(all_questions) >= _MAX_TOTAL_QUESTIONS:
            break

        questions = await _analyse_rule(rule, state)
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
        interrupt({"clarifying_questions": all_questions})

    return {
        "clarifying_questions": all_questions,
        "clarification_complete": len(all_questions) == 0,
        "current_phase": "awaiting_clarification" if all_questions else "generating_baselines",
        "progress_log": [
            f"Ambiguity detection: {len(all_questions)} clarifying question(s) generated"
            + (" — awaiting user input" if all_questions else " — proceeding")
        ],
    }


async def _analyse_rule(rule: dict, state: OptimizationState) -> list[ClarifyingQuestion]:
    rule_type = rule["rule_type"]
    description = rule["description"]

    if rule_type == "trigger":
        guidance = (
            "Analyse this TRIGGER rule description for ambiguities that could cause inconsistent detection:\n"
            "- Is the trigger condition specific enough to detect from transcript text?\n"
            "- Does it require exact phrasing or allow semantic equivalents?\n"
            "- Could partial matches count (agent-initiated vs customer-requested)?\n"
            "- Does the evaluation scope (evaluation_type/n_messages) align with when the trigger occurs?"
        )
    else:
        guidance = (
            "Analyse this ANSWER rule description for ambiguities that could cause inconsistent evaluation:\n"
            "- Does it use vague/subjective language (e.g. 'appropriately', 'effectively', 'sufficient')?\n"
            "- Is it missing specifics about what the agent must say or do?\n"
            "- Does it require knowledge outside the transcript to verify?\n"
            "- Is it unclear what constitutes partial vs. full adherence?"
        )

    prompt = (
        f"Rule ID: {rule['rule_id']}\n"
        f"Rule type: {rule_type}\n"
        f"Speaker: {rule['speaker']}\n"
        f"Evaluation type: {rule['evaluation_type']}, n_messages: {rule['n_messages']}\n"
        f"Description: {description}\n\n"
        f"{guidance}\n\n"
        "Return a JSON array of objects, each with keys:\n"
        "  question_text (string): the clarifying question\n"
        "  rationale (string): why this ambiguity matters for LLM evaluation\n\n"
        "Return at most 2 questions. If the description is clear and unambiguous, return [].\n"
        "Return ONLY the JSON array, no preamble."
    )

    try:
        response = await get_llm().ainvoke([
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
            return []
    except Exception:
        logger.warning(
            "session=%s rule_id=%s ambiguity LLM call failed",
            state["session_id"], rule["rule_id"],
        )
        return []

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
