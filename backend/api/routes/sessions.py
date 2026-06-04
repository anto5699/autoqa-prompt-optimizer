import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from agents.graph import graph_app
from agents.state import OptimizationState
from api.schemas.report import FinalReport, ReportInProgressResponse
from api.schemas.session import (
    CreateSessionResponse,
    ErrorResponse,
    ParameterSummary,
    RuleInfo,
    SessionStatusResponse,
    SubmitAnswersRequest,
    SubmitAnswersResponse,
    SubmitDescriptionsRequest,
    SubmitDescriptionsResponse,
)
from config import DEFAULT_SYSTEM_PROMPT
from utils.csv_parser import CSVParseError, parse
from utils.session_store import session_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions")


async def _run_graph(session_id: str, initial_state: OptimizationState) -> None:
    config = {"configurable": {"thread_id": session_id}}
    try:
        await graph_app.ainvoke(initial_state, config=config)
        # When interrupt() fires, ainvoke returns normally (LangGraph catches GraphInterrupt
        # internally). state.next is non-empty when the graph is paused — don't mark complete.
        state = graph_app.get_state(config)
        if state and state.next:
            logger.info("session=%s graph paused at interrupt, pending: %s", session_id, state.next)
            return
        session_store.update(session_id, {"current_phase": "complete", "optimization_complete": True})
    except Exception as exc:
        logger.error("session=%s graph error: %s", session_id, exc)
        session_store.update(session_id, {"current_phase": "error", "error": str(exc)})


@router.post("", status_code=201, response_model=CreateSessionResponse)
async def create_session(
    file: UploadFile = File(...),
    max_iterations: int = Form(8),
    accuracy_target: float = Form(0.90),
    language: str = Form("en"),
) -> CreateSessionResponse:
    if max_iterations < 1 or max_iterations > 10:
        raise HTTPException(status_code=400, detail="max_iterations must be between 1 and 10")
    if not (0.0 < accuracy_target <= 1.0):
        raise HTTPException(status_code=400, detail="accuracy_target must be between 0 and 1")

    csv_bytes = await file.read()

    try:
        conversations, rules, ground_truth_map, excluded_rules = parse(csv_bytes)
    except CSVParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session_id = str(uuid.uuid4())

    session_store.add(session_id, {
        "session_id": session_id,
        "current_phase": "awaiting_descriptions",
        "current_iteration": 0,
        "optimization_complete": False,
        "clarifying_questions": [],
        "parameter_summary": {},
        "progress_log": [],
        "_rules": rules,
        "_conversations": conversations,
        "_ground_truth_map": ground_truth_map,
        "_excluded_rules": excluded_rules,
        "_max_iterations": max_iterations,
        "_accuracy_target": accuracy_target,
        "_language": language,
    })

    rule_infos = [
        RuleInfo(
            rule_id=r["rule_id"],
            rule_type=r["rule_type"],
            speaker=r["speaker"],
            evaluation_type=r["evaluation_type"],
            n_messages=r["n_messages"],
        )
        for r in rules
    ]

    logger.info(
        "session=%s created: %d rules, %d conversations",
        session_id, len(rules), len(conversations),
    )

    return CreateSessionResponse(
        session_id=session_id,
        rules_detected=rule_infos,
        excluded_rules=excluded_rules,
        conversation_count=len(conversations),
    )


@router.post("/{session_id}/descriptions", response_model=SubmitDescriptionsResponse)
async def submit_descriptions(session_id: str, body: SubmitDescriptionsRequest) -> SubmitDescriptionsResponse:
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("current_phase") != "awaiting_descriptions":
        raise HTTPException(status_code=409, detail="Session is not awaiting descriptions")

    rules = session["_rules"]
    rules_with_desc = [
        {**r, "description": body.descriptions.get(r["rule_id"], "")}
        for r in rules
    ]

    initial_state: OptimizationState = {
        "session_id": session_id,
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "language": session["_language"],
        "conversations": session["_conversations"],
        "rules": rules_with_desc,
        "ground_truth_map": session["_ground_truth_map"],
        "excluded_rules": session["_excluded_rules"],
        "clarifying_questions": [],
        "user_answers": {},
        "clarification_complete": False,
        "current_iteration": 0,
        "max_iterations": session["_max_iterations"],
        "accuracy_target": session["_accuracy_target"],
        "parameter_records": {},
        "optimization_complete": False,
        "parameters_meeting_target": [],
        "parameters_below_target": [],
        "progress_log": [],
        "current_phase": "ingesting",
        "final_report": None,
    }

    session_store.update(session_id, {"current_phase": "ingesting"})
    asyncio.create_task(_run_graph(session_id, initial_state))
    return SubmitDescriptionsResponse(status="started")


@router.get("/{session_id}", response_model=SessionStatusResponse)
async def get_session(session_id: str) -> SessionStatusResponse:
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    config = {"configurable": {"thread_id": session_id}}
    try:
        state = graph_app.get_state(config)
        live = state.values if state and state.values else {}
    except Exception:
        live = {}

    store_phase = session.get("current_phase", "awaiting_descriptions")
    live_phase = live.get("current_phase", "")
    # session_store is authoritative: each node writes its phase at start, and ambiguity_detection
    # writes "awaiting_clarification" before calling interrupt() (LangGraph state.values won't
    # reflect interrupt; questions live in state.tasks, not state.values).
    phase = store_phase if store_phase else live_phase
    iteration = live.get("current_iteration", session.get("current_iteration", 0))
    questions = live.get("clarifying_questions") or session.get("clarifying_questions", [])
    progress = live.get("progress_log") or session.get("progress_log", [])

    parameter_summary: dict[str, ParameterSummary] = {}
    for rule_id, record in (live.get("parameter_records") or {}).items():
        parameter_summary[rule_id] = ParameterSummary(
            accuracy=record.get("current_accuracy", 0.0),
            status=record.get("status", "pending"),
        )

    rule_infos = [
        RuleInfo(
            rule_id=r["rule_id"],
            rule_type=r["rule_type"],
            speaker=r["speaker"],
            evaluation_type=r["evaluation_type"],
            n_messages=r["n_messages"],
        )
        for r in session.get("_rules", [])
    ]

    return SessionStatusResponse(
        session_id=session_id,
        current_phase=phase,
        current_iteration=iteration,
        rules=rule_infos,
        clarifying_questions=questions,
        parameter_summary=parameter_summary,
        progress_log=progress,
    )


@router.post("/{session_id}/answers", response_model=SubmitAnswersResponse)
async def submit_answers(session_id: str, body: SubmitAnswersRequest) -> SubmitAnswersResponse:
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    from langgraph.types import Command

    config = {"configurable": {"thread_id": session_id}}
    resume_input = Command(resume={"user_answers": body.answers, "clarification_complete": True})

    asyncio.create_task(_resume_graph(session_id, resume_input, config))
    return SubmitAnswersResponse(status="resumed")


async def _resume_graph(session_id: str, resume_input, config: dict) -> None:
    try:
        await graph_app.ainvoke(resume_input, config=config)
        state = graph_app.get_state(config)
        if state and state.next:
            logger.info("session=%s graph still interrupted after resume, pending: %s", session_id, state.next)
            return
        session_store.update(session_id, {"current_phase": "complete", "optimization_complete": True})
    except Exception as exc:
        logger.error("session=%s resume error: %s", session_id, exc)
        session_store.update(session_id, {"current_phase": "error", "error": str(exc)})


@router.get("/{session_id}/report")
async def get_report(session_id: str):
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    config = {"configurable": {"thread_id": session_id}}
    try:
        state = graph_app.get_state(config)
        live = state.values if state and state.values else {}
    except Exception:
        live = {}

    if not live.get("optimization_complete"):
        phase = live.get("current_phase") or session.get("current_phase", "ingesting")
        return ReportInProgressResponse(status="in_progress", current_phase=phase)

    return live.get("final_report", {})


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str) -> None:
    if not session_store.delete(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
