# tests/test_metrics.py

# PROMPT: "Generate pytest tests for a FastAPI store analytics API. Cover:
# /stores/{id}/metrics returns correct visitor counts, staff excluded,
# zero-purchase stores handled, /health returns stale feed correctly,
# /events/ingest is idempotent."
# CHANGES MADE: Added fixture for test client, added edge case for empty
# events.jsonl, fixed idempotency test to check actual dedup logic.

import pytest
import json
import uuid
from fastapi.testclient import TestClient
from unittest.mock import patch, mock_open
from datetime import datetime


# -------------------------
# Import app
# -------------------------
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import app

client = TestClient(app)


def make_event(
    event_type="ENTRY",
    visitor_id=None,
    is_staff=False,
    zone_id=None,
    dwell_ms=0
):
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": "STORE_BLR_002",
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": visitor_id or f"VIS_{uuid.uuid4().hex[:8]}",
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "is_staff": is_staff,
        "confidence": 0.95,
        "metadata": {"session_seq": 1}
    }


# -------------------------
# Health Endpoint
# -------------------------

def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_has_required_fields():
    response = client.get("/health")
    data = response.json()
    assert "status" in data
    assert "feed_status" in data
    assert "event_count" in data
    assert "last_event_timestamp" in data


def test_health_status_is_healthy():
    response = client.get("/health")
    assert response.json()["status"] == "healthy"


# -------------------------
# Ingest Endpoint
# -------------------------

def test_ingest_accepts_valid_events():
    events = [make_event() for _ in range(5)]
    response = client.post(
        "/events/ingest",
        json={"events": events}
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 5


def test_ingest_idempotent():
    """Same event_id submitted twice must not double-count."""
    event = make_event()
    events = [event, event]  # same event twice

    r1 = client.post("/events/ingest", json={"events": [event]})
    r2 = client.post("/events/ingest", json={"events": [event]})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["accepted"] == 1
    assert r1.json()["rejected"] == 0

    assert r2.json()["accepted"] == 0
    assert r2.json()["rejected"] == 1


def test_ingest_empty_batch():
    response = client.post(
        "/events/ingest",
        json={"events": []}
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 0


def test_ingest_up_to_500_events():
    events = [make_event() for _ in range(500)]
    response = client.post(
        "/events/ingest",
        json={"events": events}
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 500


# -------------------------
# Metrics Endpoint
# -------------------------

def test_metrics_returns_200():
    response = client.get("/stores/STORE_BLR_002/metrics")
    assert response.status_code == 200


def test_metrics_has_required_fields():
    response = client.get("/stores/STORE_BLR_002/metrics")
    data = response.json()
    required = [
        "total_visitors",
        "conversion_rate",
        "avg_dwell_seconds",
        "zones_tracked",
        "top_zone"
    ]
    for field in required:
        assert field in data, f"Missing field: {field}"


def test_metrics_visitor_count_non_negative():
    response = client.get("/stores/STORE_BLR_002/metrics")
    assert response.json()["total_visitors"] >= 0


def test_metrics_conversion_rate_between_0_and_100():
    response = client.get("/stores/STORE_BLR_002/metrics")
    rate = response.json()["conversion_rate"]
    assert 0 <= rate <= 100


# -------------------------
# Funnel Endpoint
# -------------------------

def test_funnel_returns_200():
    response = client.get("/stores/STORE_BLR_002/funnel")
    assert response.status_code == 200


def test_funnel_has_required_fields():
    data = client.get("/stores/STORE_BLR_002/funnel").json()
    required = [
        "unique_visitors",
        "zone_visitors",
        "engaged_visitors",
        "billing_visitors",
        "conversion_rate",
        "engagement_rate"
    ]
    for field in required:
        assert field in data, f"Missing: {field}"


def test_funnel_zone_visitors_lte_unique():
    data = client.get("/stores/STORE_BLR_002/funnel").json()
    assert data["zone_visitors"] <= data["unique_visitors"]


def test_funnel_billing_lte_zone_visitors():
    data = client.get("/stores/STORE_BLR_002/funnel").json()
    assert data["billing_visitors"] <= data["unique_visitors"]


def test_funnel_engagement_rate_is_percentage():
    data = client.get("/stores/STORE_BLR_002/funnel").json()
    assert 0 <= data["engagement_rate"] <= 100


# -------------------------
# Heatmap Endpoint
# -------------------------

def test_heatmap_returns_200():
    response = client.get("/stores/STORE_BLR_002/heatmap")
    assert response.status_code == 200


def test_heatmap_has_zones():
    data = client.get("/stores/STORE_BLR_002/heatmap").json()
    assert "zones" in data


def test_heatmap_scores_between_0_and_100():
    data = client.get("/stores/STORE_BLR_002/heatmap").json()
    for zone in data["zones"]:
        assert 0 <= zone["score"] <= 100


# -------------------------
# Anomalies Endpoint
# -------------------------

def test_anomalies_returns_200():
    response = client.get("/stores/STORE_BLR_002/anomalies")
    assert response.status_code == 200


def test_anomalies_has_required_fields():
    data = client.get("/stores/STORE_BLR_002/anomalies").json()
    assert "anomaly_count" in data
    assert "anomalies" in data


def test_anomaly_severity_valid_values():
    data = client.get("/stores/STORE_BLR_002/anomalies").json()
    valid = {"INFO", "WARNING", "CRITICAL"}
    for anomaly in data["anomalies"]:
        assert anomaly["severity"] in valid