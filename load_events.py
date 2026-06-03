import json

from analytics import AnalyticsEngine

engine = AnalyticsEngine()

with open("output/events.jsonl", "r") as f:

    for line in f:

        event = json.loads(line)

        print("FOUND EVENT:", event["event_type"])

        event_type = event["event_type"]

        # --------------------------------
        # ENTRY -> person_entry
        # --------------------------------
        if event_type in ["ENTRY", "ZONE_ENTER"]:

            print("INGESTING VISITOR")

            converted = {
                "event_type": "ZONE_ENTER",
                "camera_id": event["camera_id"],
                "timestamp": event["timestamp"].replace("Z", ""),
                "visitor_id": event["visitor_id"],
                "zone_id": event.get("zone_id")
            }

            engine.ingest(converted)
        # --------------------------------
        # ZONE_DWELL -> zone_dwell
        # --------------------------------
        elif event_type == "ZONE_DWELL":

            print("INGESTING ZONE_DWELL")

            converted = {
                "event_type": "zone_dwell",
                "camera_id": event["camera_id"],
                "timestamp": event["timestamp"].replace("Z", ""),
                "zone_id": event["zone_id"],
                "dwell_ms": event["dwell_ms"] 
            }

            engine.ingest(converted)

print("\nSTORE SUMMARY\n")

print(
    engine.get_store_summary()
)

print("\nZONE STATS\n")

print(
    engine.get_zone_stats(
        camera_id=None,
        window_minutes=1440
    )
)