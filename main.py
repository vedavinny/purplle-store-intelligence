from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from analytics import AnalyticsEngine
from event_loader import load_events
from collections import deque
import json
from datetime import datetime, timezone
import logging
import time
import uuid


app = FastAPI(
    title="Purplle Analytics API"
)

engine = AnalyticsEngine()

load_events(engine)

class EventBatch(BaseModel):
    events: List[dict]

@app.post("/events/ingest")
def ingest_events(batch: EventBatch):

    # Load existing event IDs
    existing_ids = set()
    try:
        with open("output/events.jsonl", "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    existing_ids.add(e.get("event_id"))
                except Exception:
                    continue
    except FileNotFoundError:
        pass

    accepted = 0
    rejected = 0

    with open("output/events.jsonl", "a") as f:
        for event in batch.events:
            eid = event.get("event_id")
            if eid and eid in existing_ids:
                rejected += 1
                continue
            f.write(json.dumps(event) + "\n")
            existing_ids.add(eid)
            engine.ingest(event)
            accepted += 1

    return {"accepted": accepted, "rejected": rejected}

@app.get("/analytics/events")
def recent_events():

    events = deque(maxlen=20)

    try:

        with open(
            "output/events.jsonl",
            "r"
        ) as f:

            for line in f:

                events.append(
                    json.loads(line)
                )

    except FileNotFoundError:

        return {
            "events": []
        }

    return {
        "count": len(events),
        "events": list(events)
    }

logging.basicConfig(
    format='{"trace_id":"%(trace_id)s","endpoint":"%(endpoint)s","latency_ms":%(latency_ms)s,"status":%(status)s}',
    level=logging.INFO
)

@app.middleware("http")
async def log_requests(request, call_next):
    trace_id = str(uuid.uuid4())[:8]
    start = time.time()
    response = await call_next(request)
    latency = round((time.time() - start) * 1000, 1)
    logging.info(
        "",
        extra={
            "trace_id": trace_id,
            "endpoint": request.url.path,
            "latency_ms": latency,
            "status": response.status_code
        }
    )
    return response

@app.get("/analytics/top-zone")
def top_zone():

    zones = engine.get_zone_stats(
        camera_id=None,
        window_minutes=1440
    )

    if not zones["zones"]:

        return {
            "message": "No zone data"
        }

    top = max(
        zones["zones"],
        key=lambda z: z["visitor_count"]
    )

    return top
@app.get("/analytics/kpi")
def kpi():

    summary = engine.get_store_summary()

    zones = engine.get_zone_stats(
        camera_id=None,
        window_minutes=1440
    )

    top_zone = None

    if zones["zones"]:

        top_zone = max(
            zones["zones"],
            key=lambda z: z["visitor_count"]
        )["zone_id"]

    return {
        "total_visitors":
            summary["total_visitors_today"],

        "avg_dwell_seconds":
            summary["avg_dwell_seconds"],

        "zones_tracked":
            summary["zones_tracked"],

        "top_zone":
            top_zone
    }

@app.get("/analytics/anomalies")
def anomalies():

    anomalies_list = []
    funnel_data = funnel()
    summary = engine.get_store_summary()
    zones = engine.get_zone_stats(
        camera_id=None,
        window_minutes=1440
    )

    # -------------------------
    # Dead Zone
    # -------------------------
    if len(zones["zones"]) == 0:
        anomalies_list.append({
            "type": "DEAD_ZONE",
            "severity": "WARNING",
            "message": "No zone activity detected",
            "suggested_action": "Verify camera coverage and check if zone is accessible to customers"
        })

    # -------------------------
    # Low Visitor Volume
    # -------------------------
    if funnel_data["unique_visitors"] < 5:
        anomalies_list.append({
            "type": "LOW_TRAFFIC",
            "severity": "INFO",
            "message": f"Very low visitor count: {funnel_data['unique_visitors']}",
            "suggested_action": "Check entry camera feed and verify store is open"
        })

    # -------------------------
    # Low Conversion
    # -------------------------
    if (
        funnel_data["unique_visitors"] > 5
        and funnel_data["conversion_rate"] < 10
    ):
        anomalies_list.append({
            "type": "LOW_CONVERSION",
            "severity": "WARNING",
            "message": f"Conversion rate is low: {funnel_data['conversion_rate']}%",
            "suggested_action": "Investigate billing funnel drop-off and improve zone-to-counter navigation"
        })

    # -------------------------
    # High Abandonment
    # -------------------------
    if funnel_data["abandonment_rate"] > 80 if "abandonment_rate" in funnel_data else funnel_data.get("conversion_rate", 100) < 20:
        anomalies_list.append({
            "type": "HIGH_ABANDONMENT",
            "severity": "WARNING",
            "message": f"High abandonment: {round(100 - funnel_data['conversion_rate'], 2)}% visitors did not convert",
            "suggested_action": "Review billing zone layout, reduce queue wait time, and check staff availability at counter"
        })

    # -------------------------
    # Zone with zero dwell
    # -------------------------
    for zone in zones["zones"]:
        if (
            zone["visitor_count"] > 3
            and zone["avg_dwell_seconds"] == 0
        ):
            anomalies_list.append({
                "type": "ZERO_DWELL_ZONE",
                "severity": "INFO",
                "message": f"Zone {zone['zone_id']} has visitors but zero avg dwell",
                "suggested_action": "Check zone signage, product placement, and staff engagement in this area"
            })

    # -------------------------
    # Stale feed
    # -------------------------
    health_data = health()
    if health_data.get("stale_feed"):
        anomalies_list.append({
            "type": "STALE_FEED",
            "severity": "WARNING",
            "message": "Camera feed data is stale (>10 min old)",
            "suggested_action": "Check camera connection and restart feed ingestion pipeline"
        })

    return {
        "anomaly_count": len(anomalies_list),
        "data_confidence": "medium",
        "anomalies": anomalies_list
    }


@app.get("/health")
def health():

    events = []

    try:

        with open(
            "output/events.jsonl",
            "r"
        ) as f:

            for line in f:

                try:

                    event = json.loads(line)

                    if (
                        isinstance(event, dict)
                        and "timestamp" in event
                    ):

                        events.append(event)

                except Exception:

                    continue

    except FileNotFoundError:

        return {
            "status": "healthy",
            "feed_status": "STALE_FEED",
            "stale_feed": True,
            "event_count": 0,
            "last_event_timestamp": None
        }

    if len(events) == 0:

        return {
            "status": "healthy",
            "feed_status": "STALE_FEED",
            "stale_feed": True,
            "event_count": 0,
            "last_event_timestamp": None
        }

    latest_event = max(
        events,
        key=lambda e:
            e["timestamp"]
    )

    last_ts = latest_event[
        "timestamp"
    ]

    try:

        event_time = datetime.fromisoformat(
            last_ts.replace(
                "Z",
                "+00:00"
            )
        )

        age_seconds = (
            datetime.now(
                timezone.utc
            )
            - event_time
        ).total_seconds()

        stale_feed = (
            age_seconds > 600
        )

    except Exception:

        stale_feed = True

    return {
        "status": "healthy",
        "feed_status":
            (
                "STALE_FEED"
                if stale_feed
                else "LIVE"
            ),
        "stale_feed":
            stale_feed,
        "event_count":
            len(events),
        "last_event_timestamp":
            last_ts
    }

@app.get("/analytics/funnel")
def funnel():

    unique_visitors = set()
    zone_visitors = set()
    engaged_visitors = set()
    billing_visitors = set()

    try:
        with open("output/events.jsonl", "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                visitor_id = event.get("visitor_id")
                if not visitor_id:
                    continue

                etype = event.get("event_type")

                unique_visitors.add(visitor_id)

                if etype == "ZONE_ENTER":
                    zone_visitors.add(visitor_id)

                # ✅ ZONE_DWELL or long ZONE_EXIT = engaged
                elif etype == "ZONE_DWELL":
                    engaged_visitors.add(visitor_id)

                elif etype == "ZONE_EXIT":
                    dwell_ms = event.get("dwell_ms", 0)
                    if dwell_ms >= 5000:  # 5s+ = engaged
                        engaged_visitors.add(visitor_id)

                # ✅ BILLING = converted
                elif etype == "BILLING":
                    billing_visitors.add(visitor_id)

    except FileNotFoundError:
        return {"error": "events.jsonl not found"}

    total = len(unique_visitors)

    engagement_rate = round(
        (len(engaged_visitors) / total) * 100, 2
    ) if total > 0 else 0

    conversion_rate = round(
        (len(billing_visitors) / total) * 100, 2
    ) if total > 0 else 0

    return {
        "unique_visitors": total,
        "zone_visitors": len(zone_visitors),
        "engaged_visitors": len(engaged_visitors),
        "billing_visitors": len(billing_visitors),
        "conversion_rate": conversion_rate,
        "engagement_rate": engagement_rate,
        "data_confidence": "medium"
    }
@app.get("/analytics/reentry")
def reentry():

    events = []

    try:

        with open(
            "output/events.jsonl",
            "r"
        ) as f:

            for line in f:

                try:

                    event = json.loads(line)

                    if (
                        event.get(
                            "event_type"
                        ) == "REENTRY"
                    ):

                        events.append(event)

                except Exception:

                    continue

    except FileNotFoundError:

        pass

    return {
        "reentry_count":
            len(events),

        "events":
            events
    }

@app.get("/analytics/heatmap")
def heatmap():

    zones = engine.get_zone_stats(
        camera_id=None,
        window_minutes=1440
    )

    total_sessions = sum(z["visitor_count"] for z in zones["zones"])
    data_confidence = "low" if total_sessions < 20 else "high"

    if not zones["zones"]:

        return {
            "zones": []
        }

    max_visitors = max(
        zone["visitor_count"]
        for zone in zones["zones"]
    )

    results = []

    for zone in zones["zones"]:

        score = 0

        if max_visitors > 0:

            score = round(
                (
                    zone["visitor_count"]
                    / max_visitors
                )
                * 100,
                2
            )

        results.append(
            {
                "zone_id":
                    zone["zone_id"],

                "score":
                    score,

                "visitor_count":
                    zone["visitor_count"],

                "avg_dwell_seconds":
                    zone[
                        "avg_dwell_seconds"
                    ]
            }
        )

    return {
        "zones": results,
         "data_confidence": data_confidence
    }
@app.get("/analytics/summary")
def summary():

    return engine.get_store_summary()


@app.get("/analytics/zones")
def zones():

    return engine.get_zone_stats(
        camera_id=None,
        window_minutes=1440
    )
@app.get("/stores/{store_id}/funnel")
def store_funnel(store_id: str):
    return funnel()

@app.get("/stores/{store_id}/heatmap")
def store_heatmap(store_id: str):
    return heatmap()

@app.get("/stores/{store_id}/anomalies")
def store_anomalies(store_id: str):
    return anomalies()

@app.get("/stores/{store_id}/metrics")
def metrics(store_id: str):

    summary = engine.get_store_summary()

    zones = engine.get_zone_stats(
        camera_id=None,
        window_minutes=1440
    )

    # Get funnel data directly
    funnel_data = funnel()

    top_zone = None
    if zones["zones"]:
        top_zone = max(
            zones["zones"],
            key=lambda z: z["visitor_count"]
        )["zone_id"]

    return {
        "total_visitors": funnel_data["unique_visitors"],  # ✅ use funnel count
        "conversion_rate": funnel_data["conversion_rate"],  # ✅ real value
        "engagement_rate": funnel_data["engagement_rate"],  # ✅ add this
        "zone_visitors": funnel_data["zone_visitors"],
        "engaged_visitors": funnel_data["engaged_visitors"],
        "billing_visitors": funnel_data["billing_visitors"],
        "avg_dwell_per_zone": {
            z["zone_id"]: z["avg_dwell_seconds"]
            for z in zones["zones"]
        },
        "queue_depth": 0,
        "abandonment_rate": round(
            100 - funnel_data["conversion_rate"], 2
        ),
        "avg_dwell_seconds": summary["avg_dwell_seconds"],
        "zones_tracked": summary["zones_tracked"],
        "top_zone": top_zone,
        "data_confidence": "medium",
    }