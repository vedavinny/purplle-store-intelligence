# Engineering Decisions

## Decision 1: YOLOv8n

AI Suggestion:
Use a lightweight detector for real-time performance.

Chosen:
YOLOv8n

Why:
The challenge prioritizes event generation and analytics over maximum detection accuracy. YOLOv8n provides a strong balance between speed and accuracy.

Trade-off:
Slightly lower accuracy than larger YOLO variants.

---

## Decision 2: ByteTrack

AI Suggestion:
Use a modern multi-object tracker.

Chosen:
ByteTrack

Why:
ByteTrack performs well in crowded scenes and maintains stable track identities.

Trade-off:
Track IDs can occasionally change during occlusion.

---

## Decision 3: JSONL Event Storage

AI Suggestion:
Store generated events in a structured format.

Chosen:
JSONL

Why:
Easy debugging, portability, and rapid development.

Trade-off:
Not suitable for large-scale production workloads.

---

## Decision 4: Polygon-Based Zones

AI Suggestion:
Represent store areas using configurable polygons.

Chosen:
Polygon zones.

Why:
Allows flexible store layouts without retraining models.

Trade-off:
Requires manual calibration.

---

## Decision 5: Billing Detection

Chosen:
Billing area dwell heuristic.

Why:
Challenge dataset did not provide reliable synchronized POS events for all customers.

Trade-off:
Billing activity is inferred rather than directly confirmed.

---

## Decision 6: Idempotent Event Ingestion

Chosen:
Duplicate event rejection based on event_id.

Why:
Prevents double counting and satisfies production reliability requirements.

Trade-off:
Requires maintaining previously seen event IDs.

---

## Decision 7: Structured Logging

Chosen:
Middleware-based structured logging.

Why:
Provides request tracing, latency monitoring, and production observability with minimal complexity.

Fields Logged:
- trace_id
- endpoint
- latency_ms
- status_code

Trade-off:
Logs are emitted to stdout rather than a centralized logging platform.

---

## AI Assistance Disclosure

AI tools were used to:

* Brainstorm architecture options
* Generate boilerplate test scaffolding
* Review API design
* Improve documentation structure

All implementation decisions, debugging, event logic, detector calibration, testing validation, and final integration were performed manually and verified against challenge requirements.

---

## Known Limitations

* Staff classification is not automated.
* Queue join/abandon analytics are not implemented.
* Appearance-based re-identification is not available.
* Single-camera assumption.
* Zone boundary jitter can affect counts near edges.
* Billing events are heuristic-based rather than POS-confirmed.
* Current logging is console-based.
* Future versions could integrate ELK, Grafana, or OpenTelemetry for centralized observability.

---

## Future Improvements

* Multi-camera tracking
* Staff uniform classifier
* Queue analytics
* Real-time Kafka streaming
* PostgreSQL backend
* POS integration
* Appearance-based ReID
* Advanced dwell modeling
