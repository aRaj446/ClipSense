"""
Render Progress Store

Lightweight in-memory store for FFmpeg render progress.
Written by agents during encoding, read by SSE endpoints.

Structure per job_id:
    {
        "stage":    str,
        "percent":  0–100,          # overall job percent
        "message":  str,
        "steps":    list[StepEntry], # ordered pipeline steps
        "ts":       float,
    }

Each StepEntry:
    { "key": str, "label": str, "status": "pending"|"active"|"done"|"failed", "percent": 0–100 }

Entries are automatically evicted after TTL_SECONDS to prevent unbounded growth.
"""

import time
import threading
from typing import TypedDict

TTL_SECONDS = 3600  # 1 hour


class StepEntry(TypedDict):
    key:     str
    label:   str
    status:  str   # pending | active | done | failed
    percent: int


class ProgressEntry(TypedDict):
    stage:   str
    percent: int
    message: str
    steps:   list[StepEntry]
    ts:      float


_store: dict[str, ProgressEntry] = {}
_lock  = threading.Lock()


def set_progress(
    job_id: str,
    stage: str,
    percent: int,
    message: str = "",
    steps: list[StepEntry] | None = None,
) -> None:
    with _lock:
        existing_steps = _store.get(job_id, {}).get("steps", [])
        _store[job_id] = {
            "stage":   stage,
            "percent": max(0, min(100, percent)),
            "message": message,
            "steps":   steps if steps is not None else existing_steps,
            "ts":      time.time(),
        }


def set_step(
    job_id: str,
    key: str,
    status: str,
    percent: int = 0,
    message: str = "",
    overall_percent: int | None = None,
) -> None:
    """
    Update a single named step within the job's steps list.
    Creates the step if it doesn't exist yet.
    """
    with _lock:
        entry = _store.get(job_id)
        if not entry:
            return
        steps = list(entry["steps"])
        for i, s in enumerate(steps):
            if s["key"] == key:
                steps[i] = {**s, "status": status, "percent": max(0, min(100, percent))}
                break
        entry["steps"]   = steps
        entry["message"] = message or entry["message"]
        if overall_percent is not None:
            entry["percent"] = max(0, min(100, overall_percent))
        entry["ts"] = time.time()


def init_steps(job_id: str, steps: list[StepEntry]) -> None:
    """Initialise the steps list for a job (call before any set_step)."""
    with _lock:
        entry = _store.get(job_id)
        if entry:
            entry["steps"] = steps
            entry["ts"]    = time.time()


def get_progress(job_id: str) -> ProgressEntry | None:
    with _lock:
        entry = _store.get(job_id)
        if entry and time.time() - entry["ts"] > TTL_SECONDS:
            del _store[job_id]
            return None
        return entry


def clear_progress(job_id: str) -> None:
    with _lock:
        _store.pop(job_id, None)


def evict_stale() -> None:
    """Remove entries older than TTL. Call periodically if needed."""
    now = time.time()
    with _lock:
        stale = [k for k, v in _store.items() if now - v["ts"] > TTL_SECONDS]
        for k in stale:
            del _store[k]
