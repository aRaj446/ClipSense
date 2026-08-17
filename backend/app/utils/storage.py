"""
Storage Utility

Defines directory constants and the MediaStorage abstraction.

MediaStorage responsibilities:
    - Create an isolated workspace per job (local filesystem today)
    - Provide a local path for input files (download from S3 later)
    - Provide a local path for the output file
    - Clean up the workspace on success, failure, or cancellation

MoviePy and FFmpeg always operate on local file paths returned by
MediaStorage — they are never responsible for S3 or network I/O.

Workspace layout (per job):
    {WORKSPACE_ROOT}/{job_id}/
        input/          — downloaded/copied input files
        tmp/            — intermediate assets (clips, SRT, concat)
        output/         — final rendered output before moving to TRAILERS_DIR

WORKSPACE_ROOT defaults to the system temp directory but can be overridden
via the WORKSPACE_ROOT environment variable. On EC2 this should point to
a fast EBS volume (e.g. /mnt/workspace).
"""

import os
import shutil
import logging
import tempfile
from contextlib import contextmanager

logger = logging.getLogger(__name__)

UPLOAD_DIR        = "app/uploads"
METADATA_DIR      = "app/metadata"
TRAILERS_DIR      = "app/trailers"
SMART_UPLOAD_DIR  = "app/uploads/smart"
DB_PATH           = "app/clipsense.db"

# Root directory for per-job workspaces.
# Override via WORKSPACE_ROOT env var on EC2 to point at a fast EBS volume.
_WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", "")


def _workspace_root() -> str:
    """Return the effective workspace root, falling back to system temp."""
    root = _WORKSPACE_ROOT.strip()
    if root:
        os.makedirs(root, exist_ok=True)
        return root
    return tempfile.gettempdir()


def ensure_directories():
    os.makedirs(UPLOAD_DIR,       exist_ok=True)
    os.makedirs(METADATA_DIR,     exist_ok=True)
    os.makedirs(TRAILERS_DIR,     exist_ok=True)
    os.makedirs(SMART_UPLOAD_DIR, exist_ok=True)


# ── MediaStorage ──────────────────────────────────────────────────────────────

class WorkspaceContext:
    """
    Isolated per-job workspace on the local filesystem.

    Provides:
        workspace_dir   — root dir for this job
        input_dir       — place input files here
        tmp_dir         — intermediate assets (clips, SRT, concat)
        output_dir      — final output before moving to TRAILERS_DIR

    Cleanup:
        Call cleanup() explicitly, or use MediaStorage.workspace() as a
        context manager which calls cleanup() in its finally block.

    Local-only today. To add S3 support later:
        - Override resolve_input() to download from S3 into input_dir
        - Override store_output() to upload from output_dir to S3
        - The rest of the pipeline (MoviePy, FFmpeg) is unchanged
    """

    def __init__(self, job_id: str, root: str):
        self.job_id        = job_id
        self.workspace_dir = os.path.join(root, job_id)
        self.input_dir     = os.path.join(self.workspace_dir, "input")
        self.tmp_dir       = os.path.join(self.workspace_dir, "tmp")
        self.output_dir    = os.path.join(self.workspace_dir, "output")
        for d in (self.input_dir, self.tmp_dir, self.output_dir):
            os.makedirs(d, exist_ok=True)
        logger.debug("workspace: created %s", self.workspace_dir)

    def resolve_input(self, source_path: str) -> str:
        """
        Return a local path for the given input file.

        Local: returns source_path unchanged (file already on disk).
        S3 (future): download to self.input_dir and return local path.
        """
        return os.path.normpath(os.path.abspath(source_path))

    def tmp_path(self, filename: str) -> str:
        """Return an absolute path inside tmp_dir for a named temp file."""
        return os.path.join(self.tmp_dir, filename)

    def output_path(self, filename: str) -> str:
        """Return an absolute path inside output_dir for the final output."""
        return os.path.join(self.output_dir, filename)

    def cleanup(self) -> None:
        """
        Remove the entire workspace directory tree.
        Safe to call multiple times — ignores errors if already deleted.
        """
        if os.path.isdir(self.workspace_dir):
            shutil.rmtree(self.workspace_dir, ignore_errors=True)
            logger.debug("workspace: cleaned up %s", self.workspace_dir)


class MediaStorage:
    """
    Factory for per-job WorkspaceContext instances.

    Usage (explicit cleanup):
        ws = MediaStorage().workspace_for(job_id)
        try:
            local_input = ws.resolve_input(raw_footage_path)
            ...
        finally:
            ws.cleanup()

    Usage (context manager — cleanup guaranteed):
        with MediaStorage().workspace(job_id) as ws:
            local_input = ws.resolve_input(raw_footage_path)
            ...
    """

    def workspace_for(self, job_id: str) -> WorkspaceContext:
        """Create and return a new WorkspaceContext for the given job."""
        return WorkspaceContext(job_id, _workspace_root())

    @contextmanager
    def workspace(self, job_id: str):
        """Context manager that creates a workspace and cleans it up on exit."""
        ws = self.workspace_for(job_id)
        try:
            yield ws
        finally:
            ws.cleanup()
