import threading
from typing import Any, Dict, Optional


class SessionStore:
    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def add(self, session_id: str, data: Dict[str, Any]) -> None:
        with self._lock:
            self._store[session_id] = data

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._store.get(session_id)

    def update(self, session_id: str, patch: Dict[str, Any]) -> None:
        with self._lock:
            if session_id in self._store:
                self._store[session_id].update(patch)

    def append_log(self, session_id: str, message: str) -> None:
        with self._lock:
            if session_id in self._store:
                self._store[session_id].setdefault("progress_log", []).append(message)

    def append_trace(self, session_id: str, entry: dict) -> None:
        with self._lock:
            if session_id in self._store:
                self._store[session_id].setdefault("trace_log", []).append(entry)

    def set_node_progress(self, session_id: str, node: str, step: int, total: int) -> None:
        with self._lock:
            if session_id in self._store:
                self._store[session_id]["node_progress"] = {"node": node, "step": step, "total": total}

    def get_trace(self, session_id: str) -> list:
        with self._lock:
            session = self._store.get(session_id)
            return list(session.get("trace_log", [])) if session else []

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._store.pop(session_id, None) is not None


session_store = SessionStore()
