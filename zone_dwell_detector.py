from ultralytics import YOLO
import supervision as sv
import cv2
import uuid

from event_logger import create_event, log_event

# -----------------------------
# YOLO
# -----------------------------
model = YOLO("yolov8n.pt")

# -----------------------------
# Tracker
# -----------------------------
tracker = sv.ByteTrack()

# -----------------------------
# Video
# -----------------------------
cap = cv2.VideoCapture("videos/Store 2/zone.mp4")

FPS = cap.get(cv2.CAP_PROP_FPS)

# -----------------------------
# SKINCARE ZONE
# -----------------------------
ZONE_X1 = 0
ZONE_Y1 = 340
ZONE_X2 = 1280
ZONE_Y2 = 650

BUFFER = 20

# -----------------------------
# Stability Thresholds
# -----------------------------
ENTER_THRESHOLD = 2
EXIT_THRESHOLD = 5

# -----------------------------
# State
# -----------------------------
track_frames = {}
zone_alert_sent = set()
visitor_map = {}
inside_last_frame = {}
session_counter = {}
inside_counter = {}
outside_counter = {}

while True:

    ret, frame = cap.read()

    if not ret:
        break

    results = model(
        frame,
        classes=[0],
        verbose=False
    )[0]

    detections = sv.Detections.from_ultralytics(results)
    detections = tracker.update_with_detections(detections)

    # -----------------------------
    # Draw Zone
    # -----------------------------
    cv2.rectangle(
        frame,
        (ZONE_X1, ZONE_Y1),
        (ZONE_X2, ZONE_Y2),
        (255, 0, 0),
        3
    )

    cv2.putText(
        frame,
        "SKINCARE ZONE",
        (ZONE_X1, ZONE_Y1 - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 0, 0),
        2
    )

    if detections.tracker_id is not None:

        for i, track_id in enumerate(detections.tracker_id):

            x1, y1, x2, y2 = detections.xyxy[i]

            confidence = float(detections.confidence[i])

            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)

            # -----------------------------
            # Visitor ID
            # -----------------------------
            if track_id not in visitor_map:
                visitor_map[track_id] = (
                    "VIS_" + str(uuid.uuid4())[:8]
                )
                session_counter[track_id] = 0

            visitor_id = visitor_map[track_id]

            # -----------------------------
            # Draw Detection
            # -----------------------------
            cv2.rectangle(
                frame,
                (int(x1), int(y1)),
                (int(x2), int(y2)),
                (0, 255, 0),
                2
            )

            cv2.putText(
                frame,
                f"{visitor_id}",
                (int(x1), int(y1) - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2
            )

            cv2.circle(
                frame,
                (cx, cy),
                5,
                (0, 0, 255),
                -1
            )

            # -----------------------------
            # Zone Check
            # -----------------------------
            inside_zone = (
                (ZONE_X1 + BUFFER) < cx < (ZONE_X2 - BUFFER)
                and
                (ZONE_Y1 + BUFFER) < cy < (ZONE_Y2 - BUFFER)
            )

            # -----------------------------
            # Init State
            # -----------------------------
            if track_id not in inside_last_frame:
                inside_last_frame[track_id] = False

            if track_id not in inside_counter:
                inside_counter[track_id] = 0

            if track_id not in outside_counter:
                outside_counter[track_id] = 0

            # =============================
            # INSIDE ZONE
            # =============================
            if inside_zone:

                inside_counter[track_id] += 1
                outside_counter[track_id] = 0

                # -------------------------
                # Stable Enter
                # -------------------------
                if (
                    inside_counter[track_id] >= ENTER_THRESHOLD
                    and
                    inside_last_frame[track_id] is False
                ):

                    session_counter[track_id] += 1

                    event = create_event(
                        camera_id="CAM2",
                        visitor_id=visitor_id,
                        event_type="ZONE_ENTER",
                        zone_id="SKINCARE",
                        dwell_ms=0,
                        confidence=confidence,
                        is_staff=False,
                        metadata={
                            "session_seq": session_counter[track_id],
                            "sku_zone": "SKINCARE"
                        }
                    )

                    log_event(event)
                    print(f"ZONE_ENTER: {visitor_id}")

                    inside_last_frame[track_id] = True
                    track_frames[track_id] = 0

                # -------------------------
                # Dwell Tracking
                # -------------------------
                if inside_last_frame[track_id]:

                    if track_id not in track_frames:
                        track_frames[track_id] = 0

                    track_frames[track_id] += 1

                    dwell_seconds = track_frames[track_id] / FPS

                    cv2.putText(
                        frame,
                        f"{dwell_seconds:.1f}s",
                        (cx, cy - 20),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (255, 255, 0),
                        2
                    )

                    # -------------------------
                    # Zone Dwell Event
                    # fires once after 30s
                    # -------------------------
                    if (
                        dwell_seconds > 30
                        and
                        track_id not in zone_alert_sent
                    ):

                        session_counter[track_id] += 1

                        event = create_event(
                            camera_id="CAM2",
                            visitor_id=visitor_id,
                            event_type="ZONE_DWELL",
                            zone_id="SKINCARE",
                            dwell_ms=int(dwell_seconds * 1000),
                            confidence=confidence,
                            is_staff=False,
                            metadata={
                                "session_seq": session_counter[track_id],
                                "sku_zone": "SKINCARE",
                                "dwell_seconds": round(dwell_seconds, 1)
                            }
                        )

                        log_event(event)
                        zone_alert_sent.add(track_id)
                        print(
                            f"ZONE_DWELL: {visitor_id} "
                            f"dwell={dwell_seconds:.1f}s"
                        )

            # =============================
            # OUTSIDE ZONE
            # =============================
            else:

                outside_counter[track_id] += 1
                inside_counter[track_id] = 0

                # -------------------------
                # Stable Exit
                # -------------------------
                if (
                    outside_counter[track_id] >= EXIT_THRESHOLD
                    and
                    inside_last_frame[track_id]
                ):

                    dwell_ms = int(
                        track_frames.get(track_id, 0) / FPS * 1000
                    )

                    session_counter[track_id] += 1

                    event = create_event(
                        camera_id="CAM2",
                        visitor_id=visitor_id,
                        event_type="ZONE_EXIT",
                        zone_id="SKINCARE",
                        dwell_ms=dwell_ms,
                        confidence=confidence,
                        is_staff=False,
                        metadata={
                            "session_seq": session_counter[track_id],
                            "sku_zone": "SKINCARE",
                            "dwell_seconds": round(dwell_ms / 1000, 1)
                        }
                    )

                    log_event(event)
                    print(
                        f"ZONE_EXIT: {visitor_id} "
                        f"dwell={dwell_ms}ms"
                    )

                    inside_last_frame[track_id] = False

                    if track_id in track_frames:
                        del track_frames[track_id]

                    if track_id in zone_alert_sent:
                        zone_alert_sent.remove(track_id)

    cv2.imshow(
        "CAM2 Zone Analytics",
        frame
    )

    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()