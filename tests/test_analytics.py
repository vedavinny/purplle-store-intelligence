# tests/test_analytics.py

# PROMPT: "Generate pytest tests for an AnalyticsEngine class that ingests
# retail store events and computes metrics. Cover: ingest all event types,
# zone stats, store summary, footfall, edge cases like empty store."
# CHANGES MADE: Removed numpy-dependent heatmap tests, added edge cases
# for zero dwell, empty engine, all-staff events.

import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from analytics import AnalyticsEngine
from datetime import datetime
import uuid


def ts():
    return datetime.utcnow().isoformat() + "Z"


def make_event(etype, visitor_id=None, zone_id=None, dwell_ms=0, is_staff=False):
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": "STORE_BLR_002",
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": visitor_id or f"VIS_{uuid.uuid4().hex[:8]}",
        "event_type": etype,
        "timestamp": ts(),
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "is_staff": is_staff,
        "confidence": 0.95,
        "metadata": {"session_seq": 1}
    }


# -------------------------
# Empty Engine
# -------------------------

def test_empty_engine_summary():
    engine = AnalyticsEngine()
    summary = engine.get_store_summary()
    assert summary["total_visitors_today"] == 0
    assert summary["avg_dwell_seconds"] == 0


def test_empty_engine_zones():
    engine = AnalyticsEngine()
    zones = engine.get_zone_stats(None, 1440)
    assert zones["zones"] == []


def test_empty_engine_footfall():
    engine = AnalyticsEngine()
    footfall = engine.get_footfall(None, "hour", 24)
    assert footfall["total_visitors"] == 0


# -------------------------
# ENTRY events
# -------------------------

def test_ingest_entry_increments_visitors():
    engine = AnalyticsEngine()
    engine.ingest(make_event("ENTRY", visitor_id="VIS_001"))
    engine.ingest(make_event("ENTRY", visitor_id="VIS_002"))
    summary = engine.get_store_summary()
    assert summary["total_visitors_today"] == 2


def test_ingest_duplicate_visitor_not_double_counted():
    engine = AnalyticsEngine()
    engine.ingest(make_event("ENTRY", visitor_id="VIS_001"))
    engine.ingest(make_event("ENTRY", visitor_id="VIS_001"))
    summary = engine.get_store_summary()
    assert summary["total_visitors_today"] == 1


def test_staff_events_tracked_separately():
    engine = AnalyticsEngine()
    engine.ingest(make_event("ENTRY", visitor_id="STAFF_001", is_staff=True))
    engine.ingest(make_event("ENTRY", visitor_id="VIS_001", is_staff=False))
    assert len(engine.unique_entry_visitors) == 2


# -------------------------
# ZONE events
# -------------------------

def test_zone_enter_tracked():
    engine = AnalyticsEngine()
    engine.ingest(make_event("ZONE_ENTER", zone_id="SKINCARE", visitor_id="VIS_001"))
    assert len(engine.unique_zone_visitors) == 1


def test_zone_exit_dwell_recorded():
    engine = AnalyticsEngine()
    engine.ingest(make_event("ZONE_EXIT", zone_id="SKINCARE", dwell_ms=6000))
    assert len(engine.zone_dwells["SKINCARE"]) == 1
    assert engine.zone_dwells["SKINCARE"][0] == 6.0


def test_zone_exit_short_dwell_ignored():
    """Dwell < 2s should be ignored (jitter filter)."""
    engine = AnalyticsEngine()
    engine.ingest(make_event("ZONE_EXIT", zone_id="SKINCARE", dwell_ms=500))
    assert len(engine.zone_dwells.get("SKINCARE", [])) == 0


def test_zone_dwell_event_recorded():
    engine = AnalyticsEngine()
    engine.ingest(make_event("ZONE_DWELL", zone_id="BILLING", dwell_ms=35000))
    assert len(engine.zone_dwells["BILLING"]) == 1


def test_billing_event_marks_engaged():
    engine = AnalyticsEngine()
    engine.ingest(make_event("BILLING", visitor_id="VIS_001", zone_id="BILLING"))
    assert "VIS_001" in engine.engaged_visitors


# -------------------------
# Zone Stats
# -------------------------

def test_zone_stats_returns_correct_zones():
    engine = AnalyticsEngine()
    engine.ingest(make_event("ZONE_ENTER", zone_id="SKINCARE", visitor_id="VIS_001"))
    engine.ingest(make_event("ZONE_ENTER", zone_id="BILLING", visitor_id="VIS_002"))
    zones = engine.get_zone_stats(None, 1440)
    zone_ids = [z["zone_id"] for z in zones["zones"]]
    assert "SKINCARE" in zone_ids
    assert "BILLING" in zone_ids


def test_zone_avg_dwell_calculated():
    engine = AnalyticsEngine()
    engine.ingest(make_event("ZONE_EXIT", zone_id="BILLING", dwell_ms=10000))
    engine.ingest(make_event("ZONE_EXIT", zone_id="BILLING", dwell_ms=20000))
    zones = engine.get_zone_stats(None, 1440)
    billing = next(z for z in zones["zones"] if z["zone_id"] == "BILLING")
    assert billing["avg_dwell_seconds"] == 15.0


def test_zone_visitor_count_unique():
    engine = AnalyticsEngine()
    # Same visitor enters twice
    engine.ingest(make_event("ZONE_ENTER", zone_id="SKINCARE", visitor_id="VIS_001"))
    engine.ingest(make_event("ZONE_ENTER", zone_id="SKINCARE", visitor_id="VIS_001"))
    engine.ingest(make_event("ZONE_ENTER", zone_id="SKINCARE", visitor_id="VIS_002"))
    zones = engine.get_zone_stats(None, 1440)
    skincare = next(z for z in zones["zones"] if z["zone_id"] == "SKINCARE")
    assert skincare["visitor_count"] == 2  # unique only


# -------------------------
# Store Summary
# -------------------------

def test_store_summary_zones_tracked():
    engine = AnalyticsEngine()
    engine.ingest(make_event("ZONE_ENTER", zone_id="SKINCARE"))
    engine.ingest(make_event("ZONE_ENTER", zone_id="BILLING"))
    summary = engine.get_store_summary()
    assert summary["zones_tracked"] == 2


def test_store_summary_avg_dwell():
    engine = AnalyticsEngine()
    engine.ingest(make_event("ZONE_EXIT", zone_id="BILLING", dwell_ms=10000))
    summary = engine.get_store_summary()
    assert summary["avg_dwell_seconds"] == 10.0


# -------------------------
# Footfall
# -------------------------

def test_footfall_hour_granularity():
    engine = AnalyticsEngine()
    engine.ingest(make_event("ENTRY", visitor_id="VIS_001"))
    engine.ingest(make_event("ZONE_ENTER", visitor_id="VIS_002", zone_id="SKINCARE"))
    result = engine.get_footfall(None, "hour", 24)
    assert result["total_visitors"] >= 2


def test_footfall_empty_returns_zero():
    engine = AnalyticsEngine()
    result = engine.get_footfall(None, "minute", 1)
    assert result["total_visitors"] == 0


# -------------------------
# Queue Stats
# -------------------------

def test_queue_stats_empty():
    engine = AnalyticsEngine()
    result = engine.get_queue_stats("CAM_BILLING_01")
    assert result["queue_depth"] == 0
    assert result["estimated_wait_minutes"] == 0