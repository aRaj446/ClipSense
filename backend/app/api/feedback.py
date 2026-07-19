"""
Feedback Analysis API

Endpoints:
    POST /upload-feedback     — upload a structured feedback file (.json or .csv)
    POST /analyze-feedback    — submit raw feedback text (kept for future LLM use)
    GET  /feedback-datasets/{project_id}
    GET  /feedback-dataset/{dataset_id}
    DELETE /feedback-dataset/{dataset_id}

Pipeline order for file upload:
    1. Parse structured file   — extract FeedbackSegment list from JSON or CSV
    2. Save to SQLite          — persist segments BEFORE Agent 2 runs
    3. Video Optimization Agent — segments + metadata → recommendations + editing plan
"""

import json
import csv
import io
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.schemas.feedback import (
    AnalyzeFeedbackRequest,
    AnalysisResponse,
    FeedbackSummary,
    FeedbackSegment,
    FeedbackDatasetResponse,
    StoredSegment,
    RenameDatasetRequest,
    AnalyticsReport,
)
from app.services.feedback_structuring_agent import FeedbackStructuringAgent
from app.services.video_optimization_agent import VideoOptimizationAgent
from app.services.analytics_agent import AnalyticsAgent
from app.services.feedback_dataset_service import FeedbackDatasetService
from app.services.project_service import ProjectService
from app.db.database import get_db

router = APIRouter()

_structuring_agent  = FeedbackStructuringAgent()
_optimization_agent = VideoOptimizationAgent()
_analytics_agent    = AnalyticsAgent()
_dataset_service    = FeedbackDatasetService()
_project_service    = ProjectService()

# Accepted file extensions for structured dataset upload
_ALLOWED_EXTENSIONS = {".json", ".csv", ".txt"}


# ── File upload endpoint ──────────────────────────────────────────────────────

@router.post("/upload-feedback", response_model=AnalysisResponse, status_code=201)
async def upload_feedback_file(
    project_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Accept a structured feedback file (.json or .csv) for a project.

    Expected JSON format:
        [
          {
            "timestamp": "00:34",       // MM:SS string or null
            "topic": "Camera",
            "sentiment": "Positive",    // Positive|Negative|Neutral|Suggestion|Complaint|Praise
            "summary": "Great shot",
            "confidence": 0.92
          },
          ...
        ]

    Expected CSV format (header row required):
        timestamp,topic,sentiment,summary,confidence
        00:34,Camera,Positive,Great shot,0.92
        ,Music,Negative,Too loud,0.78

    Business logic (parsing) lives in _parse_file().
    This route only handles HTTP concerns.
    """
    project = _project_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    filename = file.filename or ""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: .json, .csv, .txt",
        )

    raw_bytes = await file.read()
    raw_text  = raw_bytes.decode("utf-8", errors="replace")

    # ── Stage 1: Parse file into FeedbackSegment list ─────────────────────────
    # .txt → FeedbackStructuringAgent (Gemini 2.5 Pro or regex fallback)
    # .json / .csv → structured parser
    try:
        if ext == ".txt":
            segments = _structuring_agent.parse(raw_text)
            source   = "file_upload_txt"
        else:
            segments = _parse_file(raw_text, ext)
            source   = "file_upload"
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not segments:
        raise HTTPException(status_code=422, detail="File contained no valid feedback segments.")

    # ── Stage 2: Persist to DB BEFORE Agent 2 runs ───────────────────────────
    dataset = _dataset_service.save_dataset(
        db=db,
        project_id=project_id,
        raw_text=raw_text,
        segments=segments,
        source=source,
    )

    # ── Stage 3: Video Optimization Agent ────────────────────────────────────
    recommendations, editing_plan = _optimization_agent.analyze(
        segments=segments,
        video_metadata=project,
    )

    positive = sum(1 for s in segments if s.sentiment in ("Positive", "Praise"))
    negative = sum(1 for s in segments if s.sentiment in ("Negative", "Complaint"))
    neutral  = sum(1 for s in segments if s.sentiment in ("Neutral", "Question", "Suggestion"))

    return AnalysisResponse(
        dataset_id=dataset.id,
        feedback_summary=FeedbackSummary(
            positive=positive,
            negative=negative,
            neutral=neutral,
        ),
        timeline_insights=segments,
        optimization_recommendations=recommendations,
        editing_plan=editing_plan,
    )


# ── Text submit endpoint (kept for future LLM integration) ───────────────────

@router.post("/analyze-feedback", response_model=AnalysisResponse)
def analyze_feedback(
    body: AnalyzeFeedbackRequest,
    db: Session = Depends(get_db),
):
    """
    Submit raw unstructured feedback text.
    Currently uses regex-based parsing.
    Will be replaced with Gemini 2.5 Pro in a future phase.
    """
    project = _project_service.get_project(body.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not body.feedback.strip():
        raise HTTPException(status_code=400, detail="Feedback text must not be empty")

    segments = _structuring_agent.parse(body.feedback)

    dataset = _dataset_service.save_dataset(
        db=db,
        project_id=body.project_id,
        raw_text=body.feedback,
        segments=segments,
        source="manual_paste",
    )

    recommendations, editing_plan = _optimization_agent.analyze(
        segments=segments,
        video_metadata=project,
    )

    positive = sum(1 for s in segments if s.sentiment in ("Positive", "Praise"))
    negative = sum(1 for s in segments if s.sentiment in ("Negative", "Complaint"))
    neutral  = sum(1 for s in segments if s.sentiment in ("Neutral", "Question", "Suggestion"))

    return AnalysisResponse(
        dataset_id=dataset.id,
        feedback_summary=FeedbackSummary(positive=positive, negative=negative, neutral=neutral),
        timeline_insights=segments,
        optimization_recommendations=recommendations,
        editing_plan=editing_plan,
    )


# ── Dataset read / delete endpoints ──────────────────────────────────────────

@router.get(
    "/feedback-datasets/{project_id}",
    response_model=list[FeedbackDatasetResponse],
)
def list_datasets(project_id: str, db: Session = Depends(get_db)):
    """Return all stored feedback datasets for a project, newest first."""
    if not _project_service.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return [_serialise(ds) for ds in _dataset_service.get_datasets_for_project(db, project_id)]


@router.get("/feedback-dataset/{dataset_id}", response_model=FeedbackDatasetResponse)
def get_dataset(dataset_id: str, db: Session = Depends(get_db)):
    """Return a single stored dataset with all its segments."""
    ds = _dataset_service.get_dataset_by_id(db, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return _serialise(ds)


@router.patch("/feedback-dataset/{dataset_id}/rename", response_model=FeedbackDatasetResponse)
def rename_dataset(dataset_id: str, body: RenameDatasetRequest, db: Session = Depends(get_db)):
    """Set a user-defined name on a stored dataset."""
    ds = _dataset_service.rename_dataset(db, dataset_id, body.name)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return _serialise(ds)


@router.get("/analytics/{dataset_id}", response_model=AnalyticsReport)
def get_analytics(dataset_id: str, db: Session = Depends(get_db)):
    """
    Run the Analytics Agent on a saved dataset.
    Returns a Power BI / Tableau-ready analytics payload.
    """
    ds = _dataset_service.get_dataset_by_id(db, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    segments = [
        FeedbackSegment(
            timestamp=seg.timestamp,
            topic=seg.topic,
            sentiment=seg.sentiment,
            summary=seg.summary,
            confidence=seg.confidence,
        )
        for seg in ds.segments
    ]
    return _analytics_agent.analyze(segments)


@router.get("/export-dataset/{dataset_id}")
def export_dataset_excel(dataset_id: str, db: Session = Depends(get_db)):
    """Export a dataset as .xlsx — segments sheet + raw text sheet."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    ds = _dataset_service.get_dataset_by_id(db, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    wb = openpyxl.Workbook()

    # ── Sheet 1: Segments ─────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Segments"
    headers = ["#", "Timestamp", "Topic", "Sentiment", "Summary", "Confidence", "Created At"]
    header_fill = PatternFill("solid", fgColor="1E293B")
    header_font = Font(bold=True, color="94A3B8")

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    sentiment_colors = {
        "Positive": "166534", "Praise": "166534",
        "Negative": "991B1B", "Complaint": "991B1B",
        "Suggestion": "92400E", "Question": "1E3A5F",
        "Neutral": "374151",
    }

    for seg in ds.segments:
        row = [
            seg.position + 1,
            seg.timestamp or "—",
            seg.topic,
            seg.sentiment,
            seg.summary,
            round(seg.confidence * 100, 1),
            seg.created_at.strftime("%Y-%m-%d %H:%M"),
        ]
        ws.append(row)
        color = sentiment_colors.get(seg.sentiment, "374151")
        ws.cell(row=ws.max_row, column=4).fill = PatternFill("solid", fgColor=color)
        ws.cell(row=ws.max_row, column=4).font = Font(color="FFFFFF", bold=True)

    ws.column_dimensions["E"].width = 60
    for col in ["A","B","C","D","F","G"]:
        ws.column_dimensions[col].width = 18

    # ── Sheet 2: Raw Feedback ─────────────────────────────────────────────────
    ws2 = wb.create_sheet("Raw Feedback")
    ws2.append(["Dataset ID", ds.id])
    ws2.append(["Project ID", ds.project_id])
    ws2.append(["Source",     ds.source])
    ws2.append(["Name",       ds.name or ""])
    ws2.append(["Created At", ds.created_at.strftime("%Y-%m-%d %H:%M:%S")])
    ws2.append([])
    ws2.append(["Raw Text"])
    ws2.cell(row=7, column=1).font = Font(bold=True)
    for line in (ds.raw_text or "").splitlines():
        ws2.append([line])
    ws2.column_dimensions["A"].width = 20
    ws2.column_dimensions["B"].width = 80

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    label = (ds.name or dataset_id[:8]).replace(" ", "_")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="clipsense_{label}.xlsx"'},
    )


@router.delete("/feedback-dataset/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: str, db: Session = Depends(get_db)):
    """Delete a stored dataset and all its segments."""
    if not _dataset_service.delete_dataset(db, dataset_id):
        raise HTTPException(status_code=404, detail="Dataset not found")


# ── Private helpers ───────────────────────────────────────────────────────────

def _parse_file(raw_text: str, ext: str) -> list[FeedbackSegment]:
    """
    Parse a structured feedback file into FeedbackSegment objects.

    Supports .json and .csv.
    Raises ValueError with a descriptive message on invalid structure.

    When Gemini 2.5 Pro is integrated, unstructured files will be pre-processed
    by the LLM before reaching this function — the output contract stays identical.
    """
    if ext == ".json":
        return _parse_json(raw_text)
    if ext == ".csv":
        return _parse_csv(raw_text)
    raise ValueError(f"Unsupported extension: {ext}")


def _parse_json(raw_text: str) -> list[FeedbackSegment]:
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError("JSON file must contain a top-level array of segment objects.")

    segments: list[FeedbackSegment] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Item at index {i} is not an object.")
        try:
            segments.append(FeedbackSegment(
                timestamp=item.get("timestamp"),
                topic=item.get("topic", "General"),
                sentiment=item.get("sentiment", "Neutral"),
                summary=str(item.get("summary", item.get("comment", ""))),
                confidence=float(item.get("confidence", 0.75)),
            ))
        except Exception as exc:
            raise ValueError(f"Invalid segment at index {i}: {exc}") from exc

    return segments


def _parse_csv(raw_text: str) -> list[FeedbackSegment]:
    reader = csv.DictReader(io.StringIO(raw_text))

    required = {"sentiment", "summary"}
    if reader.fieldnames:
        missing = required - {f.strip().lower() for f in reader.fieldnames if f}
        if missing:
            raise ValueError(
                f"CSV is missing required columns: {', '.join(missing)}. "
                f"Required: timestamp, topic, sentiment, summary, confidence"
            )

    segments: list[FeedbackSegment] = []
    for i, row in enumerate(reader):
        # Normalise keys to lowercase and strip whitespace
        row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items()}
        try:
            segments.append(FeedbackSegment(
                timestamp=row.get("timestamp") or None,
                topic=row.get("topic", "General") or "General",
                sentiment=row.get("sentiment", "Neutral") or "Neutral",
                summary=row.get("summary", row.get("comment", "")),
                confidence=float(row.get("confidence", 0.75) or 0.75),
            ))
        except Exception as exc:
            raise ValueError(f"Invalid row at line {i + 2}: {exc}") from exc

    return segments


def _serialise(ds) -> FeedbackDatasetResponse:
    return FeedbackDatasetResponse(
        id=ds.id,
        project_id=ds.project_id,
        name=ds.name,
        source=ds.source,
        created_at=ds.created_at.isoformat(),
        segment_count=len(ds.segments),
        segments=[
            StoredSegment(
                id=seg.id,
                position=seg.position,
                timestamp=seg.timestamp,
                topic=seg.topic,
                sentiment=seg.sentiment,
                summary=seg.summary,
                confidence=seg.confidence,
                created_at=seg.created_at.isoformat(),
            )
            for seg in ds.segments
        ],
    )
