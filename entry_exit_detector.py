from ultralytics import YOLO
import supervision as sv
import cv2
import uuid
import time

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
cap = cv2.VideoCapture("videos/Store 2/entry 2.mp4")

# -------------------------
# Door Line
# -------------------------
line_y = 540

# -------------------------
# Config
# -------------------------
COOLDOWN_SECONDS = 2.0
MIN_FRAMES = 8
START_TIME = time.time()
WARMUP_SECONDS = 8

# -------------------------
# State
# -------------------------
track_side = {}
visitor_map = {}
exited_visitors = {}
last_event_time = {}
side_frame_count = {}

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

    # -------------------------
    # Draw Entry Line
    # -------------------------
    cv2.line(
        frame,
        (0, line_y),
        (frame.shape[1], line_y),
        (0, 255, 255),
        3
    )

    cv2.putText(
        frame,
        "ENTRY / EXIT LINE",
        (50, line_y - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2
    )

    if detections.tracker_id is not None:

        for i, track_id in enumerate(detections.tracker_id):

            x1, y1, x2, y2 = detections.xyxy[i]

            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)

            # -------------------------
            # Visitor ID
            # -------------------------
            if track_id not in visitor_map:
                visitor_map[track_id] = (
                    "VIS_" + str(uuid.uuid4())[:8]
                )

            visitor_id = visitor_map[track_id]

            # -------------------------
            # Draw Box
            # -------------------------
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

            # -------------------------
            # Raw Side Detection
            # -------------------------
            raw_side = "inside" if cy > line_y else "outside"

            # -------------------------
            # Consecutive Frame Counter
            # -------------------------
            if track_id not in side_frame_count:
                side_frame_count[track_id] = {
                    "side": raw_side,
                    "count": 0
                }

            sc = side_frame_count[track_id]

            if sc["side"] == raw_side:
                sc["count"] += 1
            else:
                sc["side"] = raw_side
                sc["count"] = 1

            # -------------------------
            # Confirmed Side
            # None = not yet stabilized
            # -------------------------
            if sc["count"] >= MIN_FRAMES:
                confirmed_side = raw_side
            else:
                confirmed_side = track_side.get(track_id, None)

            # -------------------------
            # Not stabilized yet — skip
            # -------------------------
            if confirmed_side is None:
                continue

            # -------------------------
            # First stable detection —
            # set baseline, no event
            # -------------------------
            if track_id not in track_side:
                track_side[track_id] = confirmed_side
                continue

            # -------------------------
            # Crossing Logic
            # -------------------------
            previous_side = track_side[track_id]

            if previous_side != confirmed_side:

                if time.time() - START_TIME < WARMUP_SECONDS:
                    track_side[track_id] = confirmed_side
                    continue
                now = time.time()
                last_t = last_event_time.get(visitor_id, 0)

                if now - last_t >= COOLDOWN_SECONDS:

                    last_event_time[visitor_id] = now

                    # -------------------------
                    # ENTRY / REENTRY
                    # -------------------------
                    if (
                        previous_side == "outside"
                        and confirmed_side == "inside"
                    ):

                        event_type = (
                            "REENTRY"
                            if visitor_id in exited_visitors
                            else "ENTRY"
                        )

                        event = create_event(
                            camera_id="CAM_ENTRY_01",
                            visitor_id=visitor_id,
                            event_type=event_type,
                            zone_id=None,
                            dwell_ms=0,
                            confidence=0.95,
                            is_staff=False,
                            metadata={"session_seq": 1}
                        )

                        log_event(event)
                        print(f"{event_type}: {visitor_id}")

                    # -------------------------
                    # EXIT
                    # -------------------------
                    elif (
                        previous_side == "inside"
                        and confirmed_side == "outside"
                    ):

                        event = create_event(
                            camera_id="CAM_ENTRY_01",
                            visitor_id=visitor_id,
                            event_type="EXIT",
                            zone_id=None,
                            dwell_ms=0,
                            confidence=0.95,
                            is_staff=False,
                            metadata={"session_seq": 1}
                        )

                        log_event(event)
                        exited_visitors[visitor_id] = True
                        print(f"EXIT: {visitor_id}")

            # -------------------------
            # Update Side
            # -------------------------
            track_side[track_id] = confirmed_side

    cv2.imshow(
        "Purplle Entry Exit Detector",
        frame
    )

    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()