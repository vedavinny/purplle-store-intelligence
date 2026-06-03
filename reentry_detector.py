import json
from event_logger import create_event
from event_logger import log_event

import json

from event_logger import (
    create_event,
    log_event
)

seen_exits = set()

def check_reentry(event):

    visitor_id = event.get(
        "visitor_id"
    )

    if not visitor_id:
        return

    if event["event_type"] == "EXIT":

        seen_exits.add(
            visitor_id
        )

    elif (
        event["event_type"]
        == "ZONE_ENTER"
        and
        visitor_id in seen_exits
    ):

        reentry_event = create_event(
            camera_id=event["camera_id"],
            visitor_id=visitor_id,
            event_type="REENTRY",
            zone_id=event["zone_id"],
            confidence=event["confidence"],
            metadata={
                "session_seq": 99
            }
        )

        log_event(
            reentry_event
        )

        seen_exits.remove(
            visitor_id
        )

        print(
            f"REENTRY DETECTED: {visitor_id}"
        )