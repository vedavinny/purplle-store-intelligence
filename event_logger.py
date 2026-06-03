import json
import uuid
from datetime import datetime

EVENT_FILE = "output/events.jsonl"

STORE_ID = "STORE_BLR_002"

def create_event(
    camera_id,
    visitor_id,
    event_type,
    zone_id=None,
    dwell_ms=0,
    confidence=1.0,
    is_staff=False,
    metadata=None
):

    if metadata is None:
        metadata = {}

    return {
        "event_id": str(uuid.uuid4()),
        "store_id": STORE_ID,
        "camera_id": camera_id,
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "zone_id": zone_id,
        "dwell_ms": int(dwell_ms),
        "is_staff": is_staff,
        "confidence": float(confidence),
        "metadata": metadata
    }


def log_event(event):

    with open(EVENT_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")

    print(event)