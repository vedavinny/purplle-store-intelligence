# Purplle Retail Intelligence Platform

## Overview

This project implements a computer vision and analytics pipeline for retail stores. The system processes store video feeds, generates customer movement events, and exposes business intelligence metrics through a FastAPI service and Streamlit dashboard.

The solution tracks:

* Customer Entry / Exit
* Zone Engagement
* Re-entry Detection
* Billing Area Visits
* Funnel Analytics
* Operational Anomalies

---

## Architecture

Video Feed
↓
YOLOv8 Person Detection
↓
ByteTrack Multi-Object Tracking
↓
Event Generation
↓
JSONL Event Store
↓
Analytics Engine
↓
FastAPI Endpoints
↓
Streamlit Dashboard

---

## Features

### Detection Pipeline

* ENTRY
* EXIT
* ZONE_ENTER
* ZONE_EXIT
* REENTRY
* BILLING

### Analytics

* Visitor Count
* Conversion Rate
* Engagement Rate
* Abandonment Rate
* Zone Heatmap
* Dwell Time Analysis
* Top Zone Identification

### Operational Monitoring

* High Abandonment Detection
* Stale Camera Feed Detection
* Zero Dwell Zone Detection
* Structured Request Logging
  - trace_id
  - endpoint
  - latency_ms
  - status_code

### API

* POST /events/ingest
* GET /stores/{store_id}/metrics
* GET /stores/{store_id}/funnel
* GET /stores/{store_id}/heatmap
* GET /stores/{store_id}/anomalies
* GET /health

---

## Dashboard

The Streamlit dashboard provides:

* Store KPIs
* Customer Funnel
* Zone Analytics
* Dwell Analytics
* Anomaly Monitoring
* Pipeline Health Status

---

## Testing

* 58 Pytest Tests Passed
* 75% Statement Coverage

Coverage validated using pytest-cov.

---

## Setup

Install dependencies:

pip install -r requirements.txt

Run API:

uvicorn main:app --reload

Run Dashboard:

streamlit run dashboard.py

Run Tests:

pytest tests -v

---

## Docker

Build:

docker build -t purplle-retail .

Run:

docker run -p 8000:8000 purplle-retail

Or:

docker-compose up --build

---

## Assumptions

* Single fixed camera per store area.
* Person class only is tracked.
* Customer identity persists only within a session.
* Billing area is defined using a manually configured polygon.
* Event storage uses JSONL for simplicity.

---

## Known Limitations

* Appearance-based re-identification is not implemented.
* Staff classification is not automated.
* Billing queue analytics are not available due to limited queue visibility.
* Zone counts may be affected by tracker jitter near boundaries.
* Long-term identity persistence across cameras is not supported.

---

## Technology Stack

* Python
* FastAPI
* Streamlit
* YOLOv8
* ByteTrack
* OpenCV
* Pandas
* Pytest
* Docker
