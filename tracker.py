"""
Tracking Pipeline — YOLOv8 detection + DeepSORT multi-object tracking
Emits structured events into the shared event bus.
"""

import time
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

# NOTE: In production install: ultralytics, deep_sort_realtime
# from ultralytics import YOLO
# from deep_sort_realtime.deepsort_tracker import DeepSort


class BoundingBox:
    def __init__(self, x1, y1, x2, y2, conf, class_id):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.conf = conf
        self.class_id = class_id

    @property
    def center(self):
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def area(self):
        return (self.x2 - self.x1) * (self.y2 - self.y1)

    def to_tlwh(self):
        return [self.x1, self.y1, self.x2 - self.x1, self.y2 - self.y1]


class Track:
    """Represents a single tracked person across frames."""

    def __init__(self, track_id: int, camera_id: str):
        self.track_id = track_id
        self.camera_id = camera_id
        self.global_id = str(uuid.uuid4())
        self.first_seen = datetime.utcnow()
        self.last_seen = datetime.utcnow()
        self.positions: list[tuple] = []
        self.zone_history: list[dict] = []
        self.current_zone: Optional[str] = None
        self.zone_entry_time: Optional[datetime] = None
        self.is_active = True
        self.frame_count = 0

    def update(self, bbox: BoundingBox, zones: dict):
        self.last_seen = datetime.utcnow()
        self.positions.append(bbox.center)
        self.frame_count += 1
        if len(self.positions) > 300:
            self.positions = self.positions[-300:]

        # Zone assignment
        new_zone = self._detect_zone(bbox.center, zones)
        if new_zone != self.current_zone:
            if self.current_zone and self.zone_entry_time:
                dwell = (datetime.utcnow() - self.zone_entry_time).total_seconds()
                self.zone_history.append({
                    "zone_id": self.current_zone,
                    "entry": self.zone_entry_time.isoformat(),
                    "exit": datetime.utcnow().isoformat(),
                    "dwell_seconds": dwell,
                })
            self.current_zone = new_zone
            self.zone_entry_time = datetime.utcnow() if new_zone else None

    def _detect_zone(self, center: tuple, zones: dict) -> Optional[str]:
        """Point-in-polygon test for zone assignment (normalized coords)."""
        cx, cy = center
        for zone_id, zone in zones.items():
            polygon = np.array(zone["polygon"], dtype=np.float32)
            result = cv2.pointPolygonTest(polygon, (cx, cy), False)
            if result >= 0:
                return zone_id
        return None

    @property
    def dwell_seconds(self) -> float:
        return (self.last_seen - self.first_seen).total_seconds()

    @property
    def velocity(self) -> tuple:
        if len(self.positions) < 5:
            return (0.0, 0.0)
        dx = self.positions[-1][0] - self.positions[-5][0]
        dy = self.positions[-1][1] - self.positions[-5][1]
        return (dx, dy)


class TrackingPipeline:
    """
    End-to-end video processing pipeline:
    1. Frame capture (file or RTSP stream)
    2. YOLOv8 person detection
    3. DeepSORT multi-object tracking
    4. Zone classification
    5. Event emission
    """

    def __init__(self, camera_id, source, event_bus, analytics_engine, anomaly_detector):
        self.camera_id = camera_id
        self.source = source
        self.event_bus = event_bus
        self.analytics_engine = analytics_engine
        self.anomaly_detector = anomaly_detector

        self.running = False
        self.current_fps = 0.0
        self.zones: dict = {}
        self.tracks: dict[int, Track] = {}
        self.frame_idx = 0
        self.heatmap_grid = np.zeros((36, 64), dtype=np.float32)  # 9:16 aspect

        # Model init (replace stubs with real models)
        self._init_models()

    def _init_models(self):
        """
        Production: self.detector = YOLO("yolov8n.pt")
        Configured for person class (class_id=0), conf>=0.4, iou=0.5
        DeepSort: max_age=30, n_init=3, nn_budget=100
        """
        self.detector = None   # YOLO("yolov8n.pt")
        self.tracker = None    # DeepSort(max_age=30, n_init=3, nn_budget=100)

    def update_zones(self, zone_list: list):
        self.zones = {z["zone_id"]: z for z in zone_list}

    def stop(self):
        self.running = False

    @property
    def active_track_count(self) -> int:
        return sum(1 for t in self.tracks.values() if t.is_active)

    def _detect(self, frame: np.ndarray) -> list[BoundingBox]:
        """
        YOLOv8 inference. Returns person detections only.

        Production code:
            results = self.detector(frame, classes=[0], conf=0.4, iou=0.5, verbose=False)
            detections = []
            for r in results:
                for box in r.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    detections.append(BoundingBox(x1, y1, x2, y2, float(box.conf), 0))
            return detections
        """
        # STUB for demo — replace with real YOLO inference
        return []

    def _track(self, detections: list[BoundingBox], frame: np.ndarray) -> list:
        """
        DeepSORT tracking step. Associates detections to existing tracks.

        Production code:
            raw = [[d.to_tlwh(), d.conf, d.class_id] for d in detections]
            return self.tracker.update_tracks(raw, frame=frame)
        """
        return []

    def _update_heatmap(self, bbox: BoundingBox, frame_shape: tuple):
        """Accumulate position data into heatmap grid."""
        h, w = frame_shape[:2]
        cx = int(bbox.center[0] / w * self.heatmap_grid.shape[1])
        cy = int(bbox.center[1] / h * self.heatmap_grid.shape[0])
        cx = max(0, min(cx, self.heatmap_grid.shape[1] - 1))
        cy = max(0, min(cy, self.heatmap_grid.shape[0] - 1))
        self.heatmap_grid[cy, cx] += 1.0

    def _emit(self, event_type: str, payload: dict):
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "camera_id": self.camera_id,
            "timestamp": datetime.utcnow().isoformat(),
            **payload,
        }
        self.event_bus.append(event)
        self.analytics_engine.ingest(event)
        self.anomaly_detector.ingest(event)

    def _process_frame(self, frame: np.ndarray):
        """Per-frame processing logic."""
        detections = self._detect(frame)
        active_track_ids = set()

        track_results = self._track(detections, frame)

        for track_result in track_results:
            if not track_result.is_confirmed():
                continue

            tid = track_result.track_id
            active_track_ids.add(tid)
            bbox = track_result.to_ltrb()
            box = BoundingBox(*bbox, 1.0, 0)

            is_new = tid not in self.tracks
            if is_new:
                self.tracks[tid] = Track(tid, self.camera_id)
                self._emit("person_entry", {
                    "track_id": tid,
                    "global_id": self.tracks[tid].global_id,
                    "position": box.center,
                })

            self.tracks[tid].update(box, self.zones)
            self._update_heatmap(box, frame.shape)

            # Dwell event every 30s in a zone
            t = self.tracks[tid]
            if t.current_zone and t.zone_entry_time:
                dwell = (datetime.utcnow() - t.zone_entry_time).total_seconds()
                if dwell > 30 and self.frame_idx % 300 == 0:
                    self._emit("zone_dwell", {
                        "track_id": tid,
                        "zone_id": t.current_zone,
                        "dwell_seconds": dwell,
                        "position": box.center,
                    })

        # Detect exits
        for tid, track in list(self.tracks.items()):
            if track.is_active and tid not in active_track_ids:
                track.is_active = False
                self._emit("person_exit", {
                    "track_id": tid,
                    "global_id": track.global_id,
                    "dwell_seconds": track.dwell_seconds,
                    "zone_history": track.zone_history,
                })

        # Push heatmap snapshot every 5 minutes
        if self.frame_idx % 9000 == 0:
            normalized = self.heatmap_grid / (self.heatmap_grid.max() + 1e-6)
            self._emit("heatmap_snapshot", {
                "grid": normalized.tolist(),
                "resolution": list(self.heatmap_grid.shape),
            })

        # Crowd density check
        crowd_count = len(active_track_ids)
        if self.frame_idx % 150 == 0:
            self._emit("crowd_count", {
                "count": crowd_count,
                "zone_breakdown": self._zone_counts(active_track_ids),
            })

    def _zone_counts(self, active_ids: set) -> dict:
        counts = defaultdict(int)
        for tid in active_ids:
            z = self.tracks.get(tid, {})
            if hasattr(z, "current_zone") and z.current_zone:
                counts[z.current_zone] += 1
        return dict(counts)

    def run(self):
        """Main loop — processes video frame by frame."""
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            self._emit("pipeline_error", {"error": f"Cannot open source: {self.source}"})
            return

        self.running = True
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_delay = 1.0 / fps
        t_start = time.time()

        while self.running:
            ret, frame = cap.read()
            if not ret:
                break

            t0 = time.time()
            self._process_frame(frame)
            self.frame_idx += 1

            elapsed = time.time() - t0
            self.current_fps = 1.0 / max(elapsed, 1e-6)

            # Maintain real-time pace for streams
            sleep = frame_delay - elapsed
            if sleep > 0:
                time.sleep(sleep)

        cap.release()
        self.running = False
        self._emit("pipeline_complete", {
            "total_frames": self.frame_idx,
            "duration_seconds": time.time() - t_start,
        })
