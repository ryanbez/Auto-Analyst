from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IngestEventRequest(BaseModel):
    source_id: str = Field(..., min_length=1, max_length=120)
    dataset_uri: str = Field(..., min_length=1)
    schema_version: Optional[str] = Field(default="v1", max_length=50)
    event_time: Optional[datetime] = None
    idempotency_key: str = Field(..., min_length=1, max_length=200)
    metadata: Optional[Dict[str, Any]] = None


class IngestEventResponse(BaseModel):
    run_id: int
    status: str
    source_id: str
    dataset_uri: str
    idempotency_key: str
    deduplicated: bool


class AutopilotRunResponse(BaseModel):
    run_id: int
    source_id: str
    dataset_uri: str
    status: str
    schema_version: Optional[str]
    event_time: datetime
    idempotency_key: str
    run_metrics: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class LabelReviewRequest(BaseModel):
    prediction_id: int
    reviewed_label: str = Field(..., min_length=1, max_length=200)
    reviewer_note: Optional[str] = Field(default=None, max_length=500)


class LabelReviewResponse(BaseModel):
    prediction_id: int
    review_status: str
    reviewed_label: str


class BulkPredictionCreateRequest(BaseModel):
    run_id: int
    rows: List[Dict[str, Any]]
    default_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
