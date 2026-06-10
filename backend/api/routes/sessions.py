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
    ParameterInfo,
    ParameterSummary,
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
    model_name: str = Form(""),
    api_key_override: str = Form(""),
    base_url: str = Form(""),
) -> CreateSessionResponse:
    if max_iterations < 1 or max_iterations > 10:
        raise HTTPException(status_code=400, detail="max_iterations must be between 1 and 10")
    if not (0.0 < accuracy_target <= 1.0):
        raise HTTPException(status_code=400, detail="accuracy_target must be between 0 and 1")

    csv_bytes = await file.read()

    try:
        conversations, metric_names, ground_truth_map, excluded_parameters, na_detected_parameters = parse(csv_bytes)
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
        "_metric_names": metric_names,
        "_na_detected_parameters": na_detected_parameters,
        "_conversations": conversations,
        "_ground_truth_map": ground_truth_map,
        "_excluded_rules": excluded_parameters,
        "_max_iterations": max_iterations,
        "_accuracy_target": accuracy_target,
        "_language": language,
        "_llm_config": {"model": model_name, "api_key": api_key_override, "base_url": base_url},
    })

    parameter_infos = [
        ParameterInfo(
            parameter_name=name,
            has_na=name in na_detected_parameters,
        )
        for name in metric_names
    ]

    logger.info(
        "session=%s created: %d metrics, %d conversations",
        session_id, len(metric_names), len(conversations),
    )

    return CreateSessionResponse(
        session_id=session_id,
        parameters_detected=parameter_infos,
        excluded_parameters=excluded_parameters,
        conversation_count=len(conversations),
    )


@router.post("/{session_id}/descriptions", response_model=SubmitDescriptionsResponse)
async def submit_descriptions(session_id: str, body: SubmitDescriptionsRequest) -> SubmitDescriptionsResponse:
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("current_phase") != "awaiting_descriptions":
        raise HTTPException(status_code=409, detail="Session is not awaiting descriptions")

    original_gt_map = session["_ground_truth_map"]

    rules: list[dict] = []
    expanded_gt_map: dict[str, dict[str, str]] = {conv_id: {} for conv_id in original_gt_map}

    for metric_name, config in body.descriptions.items():
        answer_desc = config.answer_description.strip()
        if config.type == "static":
            rules.append({
                "rule_id": metric_name,
                "rule_type": "answer",
                "speaker": "agent",
                "evaluation_type": "entire",
                "n_messages": 0,
                "description": answer_desc,
            })
            for conv_id, metric_gts in original_gt_map.items():
                expanded_gt_map[conv_id][metric_name] = metric_gts.get(metric_name, "NA")
        else:  # dynamic
            trigger_desc = (config.trigger_description or "").strip()
            trigger_id = f"{metric_name}__trigger"
            answer_id = f"{metric_name}__answer"
            rules.append({
                "rule_id": trigger_id,
                "rule_type": "trigger",
                "speaker": "agent",
                "evaluation_type": "entire",
                "n_messages": 0,
                "description": trigger_desc,
            })
            rules.append({
                "rule_id": answer_id,
                "rule_type": "answer",
                "speaker": "agent",
                "evaluation_type": "entire",
                "n_messages": 0,
                "description": answer_desc,
            })
            for conv_id, metric_gts in original_gt_map.items():
                original_gt = metric_gts.get(metric_name, "NA")
                expanded_gt_map[conv_id][trigger_id] = "No" if original_gt == "NA" else "Yes"
                expanded_gt_map[conv_id][answer_id] = original_gt

    initial_state: OptimizationState = {
        "session_id": session_id,
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "language": session["_language"],
        "llm_config": session.get("_llm_config", {}),
        "conversations": session["_conversations"],
        "rules": rules,
        "ground_truth_map": expanded_gt_map,
        "excluded_rules": session["_excluded_rules"],
        "clarifying_questions": [],
        "user_answers": {},
        "clarification_complete": False,
        "clarified_rule_ids": [],
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

    na_detected = set(session.get("_na_detected_parameters", []))
    parameter_infos = [
        ParameterInfo(
            parameter_name=name,
            has_na=name in na_detected,
        )
        for name in session.get("_metric_names", [])
    ]

    return SessionStatusResponse(
        session_id=session_id,
        current_phase=phase,
        current_iteration=iteration,
        parameters=parameter_infos,
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
