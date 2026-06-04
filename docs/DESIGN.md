# Store Intelligence System — Design Document

## Overview

This system processes raw CCTV footage from Purplle's Brigade Road
Bangalore store (ST1008) and produces real-time retail analytics
through a REST API. The north star metric is offline store conversion
rate — visitors who completed a purchase divided by total unique
visitors.

---

## System Architecture

Raw CCTV Videos (5 cameras)
↓
Detection Layer (YOLOv8s + Custom Tracker)
↓
Event Stream (JSONL file)
↓
Ingest Pipeline (HTTP batches of 500)
↓
Intelligence API (FastAPI + SQLite)
↓
Live Dashboard (Rich terminal)

---

## Stage 1 — Detection Layer

### Person Detection
YOLOv8s was chosen for person detection. It runs on CPU without
a GPU and provides a good balance between speed and accuracy.
The model was pretrained on the COCO dataset which includes
people in retail environments similar to our store.

### Tracking
A custom IOU-based tracker was built instead of ByteTrack or
DeepSORT. The reason: our videos are 2 minutes each with
relatively low crowd density. A simple IOU tracker is faster,
easier to debug, and sufficient for this use case.

### Frame Skipping
Every 3rd frame is processed (5fps from 15fps source). This
triples processing speed with minimal accuracy loss since
people move slowly in retail environments.

### Zone Detection
Zones are determined by which camera captured the detection.
Each camera covers a specific zone as defined in
store_layout.json. This is simpler and more reliable than
trying to map pixel coordinates to zones.

---

## Stage 2 — Event Stream

Events are emitted as JSONL (one JSON object per line).
This format was chosen because:
- Appendable without loading entire file
- Easy to stream line by line
- Human readable for debugging
- Directly ingestable by the API

---

## Stage 3 — Intelligence API

### Framework
FastAPI was chosen for:
- Async support (handles concurrent requests efficiently)
- Automatic API documentation at /docs
- Pydantic validation (catches bad events at the door)
- Production ready with uvicorn

### Database
SQLite was chosen over PostgreSQL because:
- No separate database container needed
- Sufficient for single store analytics
- Zero configuration
- Easy to inspect with any SQLite viewer

### Idempotency
POST /events/ingest checks event_id before inserting.
Calling it twice with the same payload produces the same
result. This is critical for reliability — if the network
drops mid-ingest, retrying is safe.

### Conversion Rate Calculation
A visitor is counted as converted if they were detected in
the BILLING zone within 5 minutes before a POS transaction.
This is a time-window correlation — no customer ID needed.

---

## Stage 4 — Dashboard

A Rich terminal dashboard shows live metrics updating as
events are ingested. Chosen over a web UI for simplicity
and reliability within the time constraint.

---

## AI-Assisted Decisions

### 1. IOU Tracker vs ByteTrack
I asked Claude to compare IOU tracking vs ByteTrack for
a low-density retail environment with 2-minute clips.
Claude suggested ByteTrack would handle occlusion better
but noted IOU tracking is sufficient when crowd density
is low. I agreed and chose IOU tracking — simpler to
debug and explain in follow-up questions.

### 2. SQLite vs PostgreSQL
Claude suggested PostgreSQL for production readiness.
I overrode this decision — the challenge is single store,
single day data. SQLite handles this easily and removes
the complexity of a second Docker container. I documented
this tradeoff in CHOICES.md.

### 3. Zone Detection Strategy
Claude initially suggested pixel coordinate mapping for
zone detection (dividing the frame into regions). I
disagreed — camera-to-zone mapping is more reliable
because camera placement is fixed and known from
store_layout.json. Pixel coordinates would require
manual calibration per camera.

---

## Edge Case Handling

| Edge Case | Our Approach |
|---|---|
| Group entry | Each bounding box = one person = one ENTRY event |
| Staff detection | Visits 3+ zones OR present 1+ hour = staff |
| Re-entry | 15 minute buffer window, same visitor_id |
| Partial occlusion | Low confidence kept, not dropped |
| Empty periods | Zero events handled, API returns 0 not null |
| Camera overlap | Camera-to-zone mapping prevents double counting |
| Queue depth | Count people in BILLING zone simultaneously |
## Known Limitations

- Cross-camera visitor deduplication is not fully implemented. 
  The same physical person may get different visitor_ids on 
  different cameras. Production deployment would require 
  appearance-based ReID (OSNet) to solve this.

- Conversion rate correlation uses a 5-minute time window 
  between billing zone presence and POS transaction. This is 
  an approximation — a visitor present at billing at 12:00 
  is matched to any transaction between 11:55 and 12:05.

- Staff detection is rule-based (zone count + time threshold). 
  A uniform-based classifier would be more accurate.

- base_time in detect.py is hardcoded to match the POS 
  transaction dataset date (2026-04-10). In production, 
  timestamps would be derived from actual clip metadata.

## Future Improvements

- Replace IOU tracker with ByteTrack for better occlusion handling
- Add OSNet ReID for cross-camera person matching
- Add PostgreSQL for multi-store concurrent write support
- Add Kafka event streaming for real-time ingestion
- Add automated staff uniform detection using a fine-tuned 
  classifier
- Expand dashboard to web UI with Chart.js visualizations