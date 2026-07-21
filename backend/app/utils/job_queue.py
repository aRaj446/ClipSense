"""
Job Queue Utility

A process-wide semaphore that limits concurrent FFmpeg/Whisper/librosa jobs
to one at a time. This prevents CPU/IO contention when multiple trailer
generation requests arrive simultaneously, and eliminates the residual
SQLite write contention that WAL mode alone cannot prevent (two jobs
committing status updates at the exact same millisecond).

Usage:
    from app.utils.job_queue import job_slot

    with job_slot():
        # heavy work here — only one thread enters at a time
        ...

The context manager blocks until the slot is free, so callers queue
naturally without dropping work. There is no timeout — jobs will always
eventually run.
"""

import threading
import logging

logger = logging.getLogger(__name__)

_semaphore = threading.Semaphore(1)


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
