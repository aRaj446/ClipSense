"""
Storage Integrity Checker

Verifies that every file path stored in the database actually exists on disk.
Returns a structured report — does NOT delete or move anything.

Used by:
    - GET /admin/storage-integrity  (health/ops endpoint)
    - Phase 6 tests
    - Startup diagnostics (optional)

Report shape:
    {
        "projects": {
            "total": int,
            "missing_raw": [project_id, ...],
            "missing_sample": [project_id, ...],
            "missing_feedback": [project_id, ...],
        },
        "generations": {
            "total": int,
            "missing_output": [job_id, ...],   # done jobs whose output file is gone
            "orphaned_output": [job_id, ...],  # done jobs with output_path but no project_id
        },
        "legacy_uploads": {
            "total": int,
            "missing": [project_id, ...],
        },
        "summary": {
            "ok": bool,
            "issues": int,
        }
    }
"""

import os
import json
import logging

logger = logging.getLogger(__name__)


def check_storage_integrity(db) -> dict:
    """
    Run a full storage integrity check against the given DB session.
    Returns the report dict described in the module docstring.
    """
    from app.models.project import Project
    from app.models.smart_trailer_job import SmartTrailerJob
    from app.utils.storage import METADATA_DIR

    report: dict = {
        "projects":       {"total": 0, "missing_raw": [], "missing_sample": [], "missing_feedback": []},
        "generations":    {"total": 0, "missing_output": [], "orphaned_output": []},
        "legacy_uploads": {"total": 0, "missing": []},
        "summary":        {"ok": True, "issues": 0},
    }

    # ── Projects ──────────────────────────────────────────────────────────────
    projects = db.query(Project).all()
    report["projects"]["total"] = len(projects)
    for p in projects:
        if p.raw_footage_path and not os.path.exists(p.raw_footage_path):
            report["projects"]["missing_raw"].append(p.id)
        if p.sample_trailer_path and not os.path.exists(p.sample_trailer_path):
            report["projects"]["missing_sample"].append(p.id)
        if p.feedback_file_path and not os.path.exists(p.feedback_file_path):
            report["projects"]["missing_feedback"].append(p.id)

    # ── Generations (project-based SmartTrailerJobs) ──────────────────────────
    jobs = db.query(SmartTrailerJob).all()
    report["generations"]["total"] = len(jobs)
    for j in jobs:
        if j.status == "done" and j.output_path:
            if not os.path.exists(j.output_path):
                report["generations"]["missing_output"].append(j.id)
            if not j.project_id:
                report["generations"]["orphaned_output"].append(j.id)

    # ── Legacy uploads (JSON metadata files) ─────────────────────────────────
    if os.path.isdir(METADATA_DIR):
        for fname in os.listdir(METADATA_DIR):
            if not fname.endswith(".json") or fname.startswith("."):
                continue
            report["legacy_uploads"]["total"] += 1
            try:
                with open(os.path.join(METADATA_DIR, fname)) as f:
                    data = json.load(f)
                file_path = data.get("file_path") or data.get("raw_footage_path", "")
                if file_path and not os.path.exists(file_path):
                    pid = data.get("id", fname.replace(".json", ""))
                    report["legacy_uploads"]["missing"].append(pid)
            except Exception:
                pass

    # ── Summary ───────────────────────────────────────────────────────────────
    issues = (
        len(report["projects"]["missing_raw"])
        + len(report["projects"]["missing_sample"])
        + len(report["projects"]["missing_feedback"])
        + len(report["generations"]["missing_output"])
        + len(report["legacy_uploads"]["missing"])
    )
    report["summary"]["issues"] = issues
    report["summary"]["ok"]     = issues == 0

    if issues:
        logger.warning("StorageIntegrity: %d issue(s) found", issues)

    return report
