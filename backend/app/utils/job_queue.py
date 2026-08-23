"""
Job Queue Utility

A process-wide semaphore that limits concurrent FFmpeg/Whisper/librosa jobs
to one at a time. This prevents CPU/IO contention when multiple trailer
generation requests arrive simultaneously, and eliminates the residual
SQLite write contention that WAL mode alone cannot prevent (two jobs
committing status updates at the exact same millisecond).

Usage:
    from app.utils.job_queue import job_slot, cancel_job, is_cancelled

    with job_slot():
        # heavy work here — only one thread enters at a time
        if is_cancelled(job_id):
            return  # bail out early
        ...

The context manager blocks until the slot is free, so callers queue
naturally without dropping work. There is no timeout — jobs will always
eventually run.

Cancellation:
    cancel_job(job_id) marks a job for cancellation.
    is_cancelled(job_id) checks if a job was cancelled — call between pipeline stages.
    clear_cancelled(job_id) removes the marker after the job finishes.
"""

import threading
import logging
import subprocess

logger = logging.getLogger(__name__)

_semaphore = threading.Semaphore(1)
# IMPORTANT — thread-safety contract:
# Whisper model inference (transcript.py) is NOT thread-safe when sharing one
# model instance across concurrent calls. The semaphore=1 here serialises all
# jobs so only one Whisper call runs at a time within this process.
# If this value is ever raised above 1, transcript.py must be updated to use
# a per-call model instance or a thread-safe inference queue.

# ── Cancellation registry ─────────────────────────────────────────────────────

_cancelled_jobs: set[str] = set()
_cancel_lock = threading.Lock()
_active_processes: dict[str, subprocess.Popen] = {}
_process_lock = threading.Lock()


def cancel_job(job_id: str) -> None:
    """Mark a job for cancellation. If an FFmpeg subprocess is tracked, kill it."""
    with _cancel_lock:
        _cancelled_jobs.add(job_id)
    # Also kill any tracked subprocess for this job
    with _process_lock:
        proc = _active_processes.get(job_id)
        if proc and proc.poll() is None:
            logger.info("job_queue: killing subprocess for job %s (pid=%d)", job_id, proc.pid)
            try:
                proc.kill()
            except OSError:
                pass


def is_cancelled(job_id: str) -> bool:
    """Check if a job has been marked for cancellation."""
    with _cancel_lock:
        return job_id in _cancelled_jobs


def clear_cancelled(job_id: str) -> None:
    """Remove cancellation marker after job finishes/cleans up."""
    with _cancel_lock:
        _cancelled_jobs.discard(job_id)
    with _process_lock:
        _active_processes.pop(job_id, None)


def register_process(job_id: str, proc: subprocess.Popen) -> None:
    """Register an active subprocess for a job (so cancel_job can kill it)."""
    with _process_lock:
        _active_processes[job_id] = proc


def unregister_process(job_id: str) -> None:
    """Remove a tracked subprocess after it finishes."""
    with _process_lock:
        _active_processes.pop(job_id, None)


class job_slot:
    """Context manager that acquires the global job semaphore on enter and releases on exit."""

    def __enter__(self):
        logger.debug("job_queue: waiting for slot")
        _semaphore.acquire()
        logger.debug("job_queue: slot acquired")
        return self

    def __exit__(self, *_):
        _semaphore.release()
        logger.debug("job_queue: slot released")
