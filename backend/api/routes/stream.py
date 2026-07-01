import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agents.graph import graph_app
from utils.session_store import session_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions")


@router.get("/{session_id}/stream")
async def stream_session(session_id: str) -> StreamingResponse:
    return StreamingResponse(
        _event_generator(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _event_generator(session_id: str):
    log_cursor = 0
    last_progress_step = -1
    config = {"configurable": {"thread_id": session_id}}

    while True:
        session = session_store.get(session_id)
        if session is None:
            yield _sse_event("error", {"message": "Session not found"})
            return

        try:
            state = graph_app.get_state(config)
            live = state.values if state and state.values else {}
        except Exception:
            live = {}

        # session_store is updated at the START of each node (more current than LangGraph state,
        # which only reflects phase after a node *completes*). Prefer it except for terminal states
        # that come from _run_graph's post-graph update.
        store_phase = session.get("current_phase", "ingesting")
        live_phase = live.get("current_phase", "")
        phase = store_phase if store_phase else live_phase
        node_progress = session.get("node_progress")
        live_log: list[str] = list(live.get("progress_log") or [])
        store_log: list[str] = list(session.get("progress_log") or [])
        # Prefer whichever source has more entries — session_store wins during active nodes
        progress_log = store_log if len(store_log) >= len(live_log) else live_log

        # Emit new progress messages since last cursor
        new_messages = progress_log[log_cursor:]
        for msg in new_messages:
            yield _sse_event("progress", {
                "phase": phase,
                "message": msg,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "node_progress": node_progress,
            })
        log_cursor += len(new_messages)

        # Heartbeat: emit when node_progress changes but no new log messages (evaluator runs silently)
        if not new_messages and node_progress:
            current_step = node_progress.get("step", -1)
            if current_step != last_progress_step:
                last_progress_step = current_step
                yield _sse_event("progress", {
                    "phase": phase,
                    "message": None,
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                    "node_progress": node_progress,
                })

        if phase == "complete" or live.get("optimization_complete"):
            yield _sse_event("complete", {"session_id": session_id})
            return

        if phase == "error":
            yield _sse_event("error", {"message": session.get("error", "Unknown error")})
            return

        await asyncio.sleep(0.5)


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
