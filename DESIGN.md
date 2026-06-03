# System Design

## Objective

Build a lightweight retail intelligence platform capable of converting video feeds into business metrics.

---

## Event Model

Every detected action is represented as a structured event.

Core schema:

* event_id
* visitor_id
* event_type
* timestamp
* store_id
* camera_id
* zone_id
* confidence
* is_staff

Supported event types:

* ENTRY
* EXIT
* ZONE_ENTER
* ZONE_EXIT
* REENTRY
* BILLING

---

## Detection Pipeline

### Person Detection

YOLOv8n is used for real-time person detection.

Reason:

* Lightweight
* Fast inference
* Good accuracy for retail environments

---

### Tracking

ByteTrack associates detections across frames.

Outputs:

* Stable Track IDs
* Movement History
* Entry/Exit Transitions

---

## Entry / Exit Logic

A virtual boundary is defined near the store entrance.

Rules:

* Outside → Inside = ENTRY
* Inside → Outside = EXIT

Track history is used to reduce false transitions.

---

## Re-entry Detection

Exited visitors are stored temporarily.

If the same track returns within a configurable interval:

REENTRY event generated.

Current implementation uses short-term track continuity and event history.

---

## Zone Analytics

Zones are represented using configurable polygons.

Examples:

* SKINCARE
* BILLING

Events:

* ZONE_ENTER
* ZONE_EXIT

Dwell time is computed using zone entry timestamps.

---

## Billing Analytics

Billing activity is inferred using a billing-area polygon.

When a customer remains inside the billing zone beyond a threshold:

BILLING event generated.

---

## Analytics Engine

The analytics layer aggregates raw events.

Generated KPIs:

* Total Visitors
* Engagement Rate
* Conversion Rate
* Abandonment Rate
* Average Dwell
* Top Zone

The API uses middleware-based structured logging.

Each request generates:

- trace_id
- endpoint
- latency_ms
- status_code

These logs support debugging, monitoring, and production troubleshooting.

---

## Anomaly Detection

### HIGH_ABANDONMENT

Triggered when conversion rate falls below expected levels.

### ZERO_DWELL_ZONE

Triggered when visitors enter a zone but spend negligible time.

### STALE_FEED

Triggered when no recent events are received.

Anomalies contain:

- type
- severity
- message
- suggested_action

The suggested_action field provides operational guidance for store managers.

---

## Data Storage

JSONL event store.

Reasons:

* Simple
* Human readable
* Easy debugging
* Suitable for hackathon-scale workloads

---

## Scalability

Future improvements:

* PostgreSQL event store
* Kafka event streaming
* Multi-camera tracking
* Appearance-based ReID
* Automated staff detection
* Real POS integration
