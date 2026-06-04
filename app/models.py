from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime
import uuid

# ── Event Schema ─────────────────────────────────────────

class EventMetadata(BaseModel):
    queue_depth: Optional[int] = None
    sku_zone: Optional[str] = None
    session_seq: int = 0

class Event(BaseModel):
    event_id: str = None
    store_id: str
    camera_id: str
    visitor_id: str
    event_type: str
    timestamp: str
    zone_id: Optional[str] = None
    dwell_ms: int = 0
    is_staff: bool = False
    confidence: float = 0.9
    metadata: EventMetadata = None

    def model_post_init(self, __context):
        if self.event_id is None:
            self.event_id = str(uuid.uuid4())
        if self.metadata is None:
            self.metadata = EventMetadata()

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v):
        allowed = [
            "ENTRY", "EXIT", "ZONE_ENTER", "ZONE_EXIT",
            "ZONE_DWELL", "BILLING_QUEUE_JOIN",
            "BILLING_QUEUE_ABANDON", "REENTRY"
        ]
        if v not in allowed:
            raise ValueError(f"event_type must be one of {allowed}")
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return v

class EventBatch(BaseModel):
    events: List[Event]

# ── Response Schemas ──────────────────────────────────────

class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    duplicate: int
    errors: List[str] = []

class ZoneDwell(BaseModel):
    zone_id: str
    zone_name: str
    avg_dwell_seconds: float
    visit_count: int

class MetricsResponse(BaseModel):
    store_id: str
    date: str
    unique_visitors: int
    conversion_rate: float
    avg_dwell_per_zone: List[ZoneDwell]
    queue_depth: int
    abandonment_rate: float

class FunnelStage(BaseModel):
    stage: str
    count: int
    drop_off_pct: float

class FunnelResponse(BaseModel):
    store_id: str
    stages: List[FunnelStage]

class HeatmapZone(BaseModel):
    zone_id: str
    zone_name: str
    visit_frequency: int
    avg_dwell_seconds: float
    normalized_score: float
    data_confidence: bool

class HeatmapResponse(BaseModel):
    store_id: str
    zones: List[HeatmapZone]

class Anomaly(BaseModel):
    anomaly_id: str
    anomaly_type: str
    severity: str
    description: str
    suggested_action: str
    detected_at: str

class AnomalyResponse(BaseModel):
    store_id: str
    anomalies: List[Anomaly]

class StoreHealth(BaseModel):
    store_id: str
    status: str
    last_event_timestamp: Optional[str]
    feed_status: str

class HealthResponse(BaseModel):
    status: str
    stores: List[StoreHealth]
    timestamp: str