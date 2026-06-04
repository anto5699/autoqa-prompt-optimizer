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

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._store.pop(session_id, None) is not None


session_store = SessionStore()
