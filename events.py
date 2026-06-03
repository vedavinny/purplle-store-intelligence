"""
Event Schema Definitions
All events emitted by the pipeline conform to these Pydantic models.
Designed for Kafka / SSE / webhook delivery.
"""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


class BaseEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    camera_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    schema_version: str = "1.0"


class PersonEntryEvent(BaseEvent):
    """Emitted when a new person track is confirmed entering the frame."""
    event_type: str = "person_entry"
    track_id: int
    global_id: str                          # UUID for cross-camera linking
    position: tuple[float, float]           # (cx, cy) normalized 0-1
    confidence: float = 1.0


class PersonExitEvent(BaseEvent):
    """Emitted when a track is lost or leaves the frame."""
    event_type: str = "person_exit"
    track_id: int
    global_id: str
    dwell_seconds: float
    zone_history: list[dict] = []           # [{zone_id, entry, exit, dwell_seconds}]


class ZoneDwellEvent(BaseEvent):
    """Emitted periodically while a person remains in a zone."""
    event_type: str = "zone_dwell"
    track_id: int
    zone_id: str
    dwell_seconds: float
    position: tuple[float, float]


class ShelfInteractionEvent(BaseEvent):
    """
    Emitted when a person pauses near a shelf zone (proxy for product interest).
    Dwell >= 5s in a shelf zone triggers this.
    """
    event_type: str = "shelf_interaction"
    track_id: int
    shelf_zone_id: str
    interaction_seconds: float
    product_category: Optional[str] = None  # from zone metadata


class AnomalyEvent(BaseEvent):
    """Wrapper for anomaly detector output, delivered on the event bus."""
    event_type: str = "anomaly"
    anomaly_id: str
    anomaly_type: str                        # crowd_surge, loitering, queue_overflow, etc.
    severity: str                            # low | medium | high | critical
    description: str
    payload: dict[str, Any] = {}


class CrowdEvent(BaseEvent):
    """Periodic crowd density snapshot."""
    event_type: str = "crowd_count"
    count: int
    zone_breakdown: dict[str, int] = {}      # {zone_id: count}


class HeatmapSnapshotEvent(BaseEvent):
    """Periodic heatmap grid snapshot for archival/dashboard consumption."""
    event_type: str = "heatmap_snapshot"
    grid: list[list[float]]                  # 2D normalized occupancy grid
    resolution: list[int]                    # [rows, cols]


class PipelineStatusEvent(BaseEvent):
    """Emitted on pipeline lifecycle changes."""
    event_type: str = "pipeline_status"
    status: str                              # started | stopped | error | complete
    message: Optional[str] = None
    total_frames: Optional[int] = None
    duration_seconds: Optional[float] = None
