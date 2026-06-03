from ultralytics import YOLO
import supervision as sv
import cv2
import uuid
import time
import numpy as np

from event_logger import create_event, log_event

# -------------------------
# YOLO
# -------------------------
model = YOLO("yolov8n.pt")

# -------------------------
# Tracker
# -------------------------
tracker = sv.ByteTrack()

# -------------------------
# Camera
# -------------------------
cap = cv2.VideoCapture("videos/Store 2/billing_area.mp4")

# -------------------------
# Billing Zone
# -------------------------
BILLING_ZONE_PTS = np.array([
    [220, 220],
    [650, 220],
    [650, 600],
    [220, 600],
], dtype=np.int32)

BILLING_ZONE = sv.PolygonZone(polygon=BILLING_ZONE_PTS)

# -------------------------
# Config
# -------------------------
MIN_DWELL_MS = 3000
COOLDOWN_SECONDS = 5.0
MIN_ZONE_FRAMES = 8
ZONE_COOLDOWN = 3.0

# -------------------------
# State
# -------------------------
visitor_map = {}
zone_entry_time = {}
in_zone = {}
last_event_time = {}
billed_visitors = set()
zone_frame_count = {}
zone_confirmed = {}
last_zone_enter_time = {}  # cooldown for ZONE_ENTER spam

while True:

    ret, frame = cap.read()
    if not ret:
        break

    results = model(frame, classes=[0], verbose=False)[0]
    detections = sv.Detections.from_ultralytics(results)
    detections = tracker.update_with_detections(detections)

    # -------------------------
    # Draw Billing Zone
    # -------------------------
    cv2.polylines(
        frame,
        [BILLING_ZONE_PTS.reshape((-1, 1, 2))],
        True,
        (0, 165, 255),
        2
    )

    cv2.putText(
        frame,
        "BILLING ZONE",
        (305, 195),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 165, 255),
        2
    )

    if detections.tracker_id is not None:

        mask = BILLING_ZONE.trigger(detections=detections)
        currently_in_zone = set()

        for i, track_id in enumerate(detections.tracker_id):

            x1, y1, x2, y2 = detections.xyxy[i]
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)

            if track_id not in visitor_map:
                visitor_map[track_id] = "VIS_" + str(uuid.uuid4())[:8]
            visitor_id = visitor_map[track_id]

            # -------------------------
            # Zone Debounce
            # -------------------------
            raw_in_billing = bool(mask[i])

            if track_id not in zone_frame_count:
                zone_frame_count[track_id] = {
                    "in": raw_in_billing,
                    "count": 0
                }

            zc = zone_frame_count[track_id]

            if zc["in"] == raw_in_billing:
                zc["count"] += 1
            else:
                zc["in"] = raw_in_billing
                zc["count"] = 1

            if zc["count"] >= MIN_ZONE_FRAMES:
                in_billing = raw_in_billing
            else:
                in_billing = zone_confirmed.get(track_id, raw_in_billing)

            zone_confirmed[track_id] = in_billing

            # -------------------------
            # Draw Box
            # -------------------------
            color = (0, 165, 255) if in_billing else (0, 255, 0)
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            cv2.putText(frame, f"{visitor_id}", (int(x1), int(y1) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)

            now = time.time()

            if in_billing:

                currently_in_zone.add(track_id)

                # -------------------------
                # Zone Entry — with cooldown
                # to prevent spam
                # -------------------------
                if track_id not in in_zone:

                    last_enter = last_zone_enter_time.get(track_id, 0)

                    if now - last_enter >= ZONE_COOLDOWN:

                        in_zone[track_id] = True
                        zone_entry_time[track_id] = now
                        last_zone_enter_time[track_id] = now

                        event = create_event(
                            camera_id="CAM_BILLING_01",
                            visitor_id=visitor_id,
                            event_type="ZONE_ENTER",
                            zone_id="BILLING",
                            dwell_ms=0,
                            confidence=0.95,
                            is_staff=False,
                            metadata={"zone": "billing"}
                        )
                        log_event(event)
                        print(f"ZONE_ENTER: {visitor_id}")

                # -------------------------
                # Billing Event — once only
                # after MIN_DWELL_MS
                # -------------------------
                if (
                    track_id in zone_entry_time
                    and visitor_id not in billed_visitors
                ):
                    dwell_ms = int((now - zone_entry_time[track_id]) * 1000)

                    if dwell_ms >= MIN_DWELL_MS:
                        last_t = last_event_time.get(visitor_id, 0)

                        if now - last_t >= COOLDOWN_SECONDS:
                            last_event_time[visitor_id] = now

                            event = create_event(
                                camera_id="CAM_BILLING_01",
                                visitor_id=visitor_id,
                                event_type="BILLING",
                                zone_id="BILLING",
                                dwell_ms=dwell_ms,
                                confidence=0.95,
                                is_staff=False,
                                metadata={
                                    "zone": "billing",
                                    "dwell_seconds": round(dwell_ms / 1000, 1)
                                }
                            )
                            log_event(event)
                            billed_visitors.add(visitor_id)
                            print(f"BILLING: {visitor_id} dwell={dwell_ms}ms")

                # -------------------------
                # Draw dwell timer
                # -------------------------
                if track_id in zone_entry_time:
                    dwell_s = round(now - zone_entry_time[track_id], 1)
                    cv2.putText(
                        frame,
                        f"{dwell_s}s",
                        (int(x1), int(y2) + 20),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 165, 255),
                        2
                    )

        # -------------------------
        # Zone Exit
        # -------------------------
        for track_id in list(in_zone.keys()):

            if track_id not in currently_in_zone:

                visitor_id = visitor_map.get(track_id, "UNKNOWN")
                entry_t = zone_entry_time.get(track_id, time.time())
                dwell_ms = int((time.time() - entry_t) * 1000)

                event = create_event(
                    camera_id="CAM_BILLING_01",
                    visitor_id=visitor_id,
                    event_type="ZONE_EXIT",
                    zone_id="BILLING",
                    dwell_ms=dwell_ms,
                    confidence=0.95,
                    is_staff=False,
                    metadata={
                        "zone": "billing",
                        "dwell_seconds": round(dwell_ms / 1000, 1)
                    }
                )
                log_event(event)
                print(f"ZONE_EXIT: {visitor_id} dwell={dwell_ms}ms")

                del in_zone[track_id]
                del zone_entry_time[track_id]

    cv2.imshow("Purplle Billing Detector", frame)

    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()