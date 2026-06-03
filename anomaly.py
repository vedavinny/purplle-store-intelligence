"""
Anomaly Detection Engine
Detects: crowd surges, loitering, abandoned objects, queue overflow, unauthorized zone access.
Uses rule-based triggers + sliding window statistics.
"""

import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional


SEVERITY_RANKS = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class Anomaly:
    def __init__(self, anomaly_type: str, camera_id: str, severity: str, description: str, payload: dict):
        self.anomaly_id = str(uuid.uuid4())
        self.anomaly_type = anomaly_type
        self.camera_id = camera_id
        self.severity = severity
        self.description = description
        self.payload = payload
        self.detected_at = datetime.utcnow().isoformat()
        self.resolved = False
        self.resolved_at = None
        self.resolution_notes = ""

    def to_dict(self):
        return {
            "anomaly_id": self.anomaly_id,
            "anomaly_type": self.anomaly_type,
            "camera_id": self.camera_id,
            "severity": self.severity,
            "description": self.description,
            "payload": self.payload,
            "detected_at": self.detected_at,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at,
            "resolution_notes": self.resolution_notes,
        }


class AnomalyDetector:
    """
    Stateful anomaly detector. Ingests events and maintains sliding windows
    to detect abnormal patterns using configurable thresholds.
    """

    # ── Thresholds (operator-tunable) ──────────
    CROWD_SURGE_THRESHOLD = 30           # persons in frame
    LOITERING_THRESHOLD_SECONDS = 300    # 5 min in one zone
    QUEUE_OVERFLOW_THRESHOLD = 15        # persons in checkout zone
    CROWD_SPIKE_RATIO = 2.5              # current / rolling_avg triggers alert
    RESTRICTED_ZONE_ALERT = True

    def __init__(self):
        self.anomalies: dict[str, Anomaly] = {}
        self.crowd_history: dict = defaultdict(lambda: deque(maxlen=60))  # 60-frame rolling
        self.loiter_watch: dict = {}        # track_id -> (zone_id, first_seen)
        self.active_anomaly_types: dict = {}  # camera+type -> anomaly_id (dedup)

    # ─────────────────────────────────────────
    # Ingest
    # ─────────────────────────────────────────

    def ingest(self, event: dict):
        etype = event.get("event_type")
        cam = event.get("camera_id", "unknown")

        if etype == "crowd_count":
            self._check_crowd_surge(event, cam)

        elif etype == "zone_dwell":
            self._check_loitering(event, cam)

        elif etype == "person_entry":
            zone = event.get("zone_id")
            if zone and "restricted" in zone.lower():
                self._raise(
                    anomaly_type="unauthorized_zone_access",
                    camera_id=cam,
                    severity="high",
                    description=f"Person entered restricted zone '{zone}'",
                    payload=event,
                    dedup_key=f"{cam}:restricted:{event.get('track_id')}",
                )

    def _check_crowd_surge(self, event: dict, cam: str):
        count = event.get("count", 0)
        history = self.crowd_history[cam]
        history.append(count)

        avg = sum(history) / len(history) if history else 0

        if count >= self.CROWD_SURGE_THRESHOLD:
            self._raise(
                "crowd_surge", cam, "critical",
                f"Crowd density critical: {count} persons detected (threshold {self.CROWD_SURGE_THRESHOLD})",
                {"count": count, "threshold": self.CROWD_SURGE_THRESHOLD},
                dedup_key=f"{cam}:crowd_surge",
                auto_resolve_after_seconds=120,
            )

        elif avg > 0 and count / avg >= self.CROWD_SPIKE_RATIO:
            self._raise(
                "crowd_spike", cam, "high",
                f"Sudden crowd spike: {count} vs {avg:.0f} avg ({count/avg:.1f}x)",
                {"count": count, "rolling_avg": round(avg, 1), "ratio": round(count/avg, 2)},
                dedup_key=f"{cam}:crowd_spike",
                auto_resolve_after_seconds=60,
            )

        zone_breakdown = event.get("zone_breakdown", {})
        checkout_count = zone_breakdown.get("checkout", 0)
        if checkout_count >= self.QUEUE_OVERFLOW_THRESHOLD:
            self._raise(
                "queue_overflow", cam, "high",
                f"Checkout queue overflow: {checkout_count} persons waiting",
                {"queue_depth": checkout_count, "threshold": self.QUEUE_OVERFLOW_THRESHOLD},
                dedup_key=f"{cam}:queue_overflow",
            )

    def _check_loitering(self, event: dict, cam: str):
        dwell = event.get("dwell_seconds", 0)
        track_id = event.get("track_id")
        zone_id = event.get("zone_id", "unknown")

        if dwell >= self.LOITERING_THRESHOLD_SECONDS:
            self._raise(
                "loitering", cam, "medium",
                f"Person loitering in zone '{zone_id}' for {int(dwell//60)}m {int(dwell%60)}s",
                {"track_id": track_id, "zone_id": zone_id, "dwell_seconds": dwell},
                dedup_key=f"{cam}:loitering:{track_id}:{zone_id}",
            )

    def _raise(
        self,
        anomaly_type: str,
        camera_id: str,
        severity: str,
        description: str,
        payload: dict,
        dedup_key: Optional[str] = None,
        auto_resolve_after_seconds: Optional[int] = None,
    ):
        """Create anomaly, skipping if same dedup_key already active."""
        key = dedup_key or f"{camera_id}:{anomaly_type}"
        if key in self.active_anomaly_types:
            existing_id = self.active_anomaly_types[key]
            if existing_id in self.anomalies and not self.anomalies[existing_id].resolved:
                return  # already active, skip

        anomaly = Anomaly(anomaly_type, camera_id, severity, description, payload)
        self.anomalies[anomaly.anomaly_id] = anomaly
        if dedup_key:
            self.active_anomaly_types[key] = anomaly.anomaly_id

    # ─────────────────────────────────────────
    # Query
    # ─────────────────────────────────────────

    def get_anomalies(
        self,
        severity: Optional[str],
        resolved: bool,
        limit: int,
    ) -> list:
        filtered = [
            a for a in self.anomalies.values()
            if a.resolved == resolved
            and (severity is None or a.severity == severity)
        ]
        filtered.sort(
            key=lambda a: (SEVERITY_RANKS.get(a.severity, 0), a.detected_at),
            reverse=True,
        )
        return [a.to_dict() for a in filtered[:limit]]

    def resolve(self, anomaly_id: str, notes: str = "") -> Optional[dict]:
        a = self.anomalies.get(anomaly_id)
        if not a:
            return None
        a.resolved = True
        a.resolved_at = datetime.utcnow().isoformat()
        a.resolution_notes = notes
        return a.to_dict()
