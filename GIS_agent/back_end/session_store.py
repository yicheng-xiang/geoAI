import threading
import time


class SessionStore:
    """Thread-safe registry; each session owns an independent re-entrant lock."""

    def __init__(self):
        self._sessions = {}
        self._lock = threading.RLock()

    def get_or_create(self, session_id):
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = {
                    "map_state": None,
                    "messages": [],
                    "uploaded_dataset": None,
                    "lock": threading.RLock(),
                    "updated_at": time.time(),
                }
                self._sessions[session_id] = session
            session["updated_at"] = time.time()
            return session

    def clear(self, session_id, close_callback=None):
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            return False

        with session["lock"]:
            if close_callback is not None:
                close_callback(session)
            with self._lock:
                if self._sessions.get(session_id) is session:
                    del self._sessions[session_id]
        return True

    def contains(self, session_id):
        with self._lock:
            return session_id in self._sessions

    def __len__(self):
        with self._lock:
            return len(self._sessions)
