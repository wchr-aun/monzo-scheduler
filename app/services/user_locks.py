"""Serialize user mutations in the supported single-worker deployment."""

from threading import Lock
from weakref import WeakValueDictionary

_locks: WeakValueDictionary[str, Lock] = WeakValueDictionary()
_guard = Lock()


def user_execution_lock(user_id: str) -> Lock:
    with _guard:
        return _locks.setdefault(user_id, Lock())
