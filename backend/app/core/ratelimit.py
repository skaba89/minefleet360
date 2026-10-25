"""Limitation de débit en mémoire, par processus (US-1.05 A5, US-1.08 A3).

Limite connue et documentée (QA-32) : compteurs non partagés entre processus/instances et perdus au
redémarrage. Suffisant pour le lot 1 (une instance locale) ; à remplacer par un stockage partagé avant pilote.
"""

import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta


class FailureLimiter:
    """Compte les échecs par clé sur une fenêtre glissante ; bloque au-delà de max_failures."""

    def __init__(self, max_failures: int, window: timedelta) -> None:
        self.max_failures = max_failures
        self.window = window
        self._events: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: datetime) -> deque[datetime]:
        events = self._events[key]
        while events and events[0] <= now - self.window:
            events.popleft()
        return events

    def is_blocked(self, key: str, now: datetime) -> bool:
        with self._lock:
            return len(self._prune(key, now)) >= self.max_failures

    def record_failure(self, key: str, now: datetime) -> None:
        with self._lock:
            self._prune(key, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
