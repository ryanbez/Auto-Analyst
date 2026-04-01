from datetime import UTC, datetime
from typing import Dict, List

from fastapi import APIRouter, HTTPException, Query

from src.db.init_db import get_session
from src.db.schemas.models import AutopilotRun, LabelPrediction
from src.schemas.autopilot_schema import (
    AutopilotRunResponse,
    BulkPredictionCreateRequest,
    IngestEventRequest,
    IngestEventResponse,
    LabelReviewRequest,
    LabelReviewResponse,
)

router = APIRouter(prefix="/autopilot", tags=["autopilot"])


@router.post("/ingest-event", response_model=IngestEventResponse)
async def ingest_event(request: IngestEventRequest):
    """Create or deduplicate an ingestion event and enqueue a run record."""
    db = get_session()
    try:
        existing = (
            db.query(AutopilotRun)
            .filter(AutopilotRun.idempotency_key == request.idempotency_key)
            .first()
        )
        if existing:
            return IngestEventResponse(
                run_id=existing.run_id,
                status=existing.status,
                source_id=existing.source_id,
                dataset_uri=existing.dataset_uri,
                idempotency_key=existing.idempotency_key,
                deduplicated=True,
            )

        run = AutopilotRun(
            source_id=request.source_id,
            dataset_uri=request.dataset_uri,
            schema_version=request.schema_version,
            event_time=request.event_time or datetime.now(UTC),
            idempotency_key=request.idempotency_key,
            status="queued",
            run_metrics={"metadata": request.metadata or {}, "received_at": datetime.now(UTC).isoformat()},
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        return IngestEventResponse(
            run_id=run.run_id,
            status=run.status,
            source_id=run.source_id,
            dataset_uri=run.dataset_uri,
            idempotency_key=run.idempotency_key,
            deduplicated=False,
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create ingest event: {exc}")
    finally:
        db.close()


@router.get("/runs", response_model=List[AutopilotRunResponse])
async def list_runs(limit: int = Query(default=20, ge=1, le=200), source_id: str | None = None):
    db = get_session()
    try:
        query = db.query(AutopilotRun)
        if source_id:
            query = query.filter(AutopilotRun.source_id == source_id)
        rows = query.order_by(AutopilotRun.created_at.desc()).limit(limit).all()

        return [
            AutopilotRunResponse(
                run_id=row.run_id,
                source_id=row.source_id,
                dataset_uri=row.dataset_uri,
                status=row.status,
                schema_version=row.schema_version,
                event_time=row.event_time,
                idempotency_key=row.idempotency_key,
                run_metrics=row.run_metrics,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]
    finally:
        db.close()


@router.post("/predictions/bulk")
async def create_predictions(request: BulkPredictionCreateRequest):
    """Bootstrap endpoint for auto-label predictions from worker pipeline."""
    db = get_session()
    try:
        run = db.query(AutopilotRun).filter(AutopilotRun.run_id == request.run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="run_id not found")

        created = 0
        for idx, row in enumerate(request.rows):
            prediction = LabelPrediction(
                run_id=request.run_id,
                row_index=idx,
                predicted_label=str(row.get("predicted_label", "unknown")),
                confidence=float(row.get("confidence", request.default_confidence)),
                model_version=str(row.get("model_version", "v0")),
                decision_reason=str(row.get("decision_reason", "bootstrap")),
                row_payload=row,
                review_status="pending",
            )
            db.add(prediction)
            created += 1

        run.status = "needs_review"
        run.run_metrics = {
            **(run.run_metrics or {}),
            "predictions_created": created,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        db.commit()
        return {"created": created, "run_id": request.run_id, "status": run.status}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create predictions: {exc}")
    finally:
        db.close()


@router.post("/labels/review", response_model=LabelReviewResponse)
async def review_label(request: LabelReviewRequest):
    db = get_session()
    try:
        prediction = (
            db.query(LabelPrediction)
            .filter(LabelPrediction.prediction_id == request.prediction_id)
            .first()
        )
        if not prediction:
            raise HTTPException(status_code=404, detail="prediction_id not found")

        prediction.reviewed_label = request.reviewed_label
        prediction.reviewer_note = request.reviewer_note
        prediction.review_status = (
            "approved"
            if request.reviewed_label == prediction.predicted_label
            else "corrected"
        )

        run = db.query(AutopilotRun).filter(AutopilotRun.run_id == prediction.run_id).first()
        if run:
            run.status = "running"
            run.run_metrics = {
                **(run.run_metrics or {}),
                "last_reviewed_prediction_id": prediction.prediction_id,
                "last_review_status": prediction.review_status,
                "updated_at": datetime.now(UTC).isoformat(),
            }

        db.commit()

        return LabelReviewResponse(
            prediction_id=prediction.prediction_id,
            review_status=prediction.review_status,
            reviewed_label=prediction.reviewed_label or "",
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to review label: {exc}")
    finally:
        db.close()
