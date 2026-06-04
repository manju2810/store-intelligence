# Store Intelligence System
Real-time retail analytics from CCTV footage for Purplle Brigade Road Bangalore (ST1008)

---

## Setup in 5 Commands

```bash
git clone <your-repo-url>
cd store-intelligence
cp data/store_layout.json data/store_layout.json
docker compose up --build
python pipeline/ingest.py
```

---

## Full Setup Guide

### Prerequisites
- Docker Desktop installed and running
- Python 3.9+
- Git

### Step 1 — Clone and enter project
```bash
git clone <your-repo-url>
cd store-intelligence
```

### Step 2 — Add your video files
Copy your 5 video files into:
data/videos/CAM1.mp4
data/videos/CAM2.mp4
data/videos/CAM3.mp4
data/videos/CAM4.mp4
data/videos/CAM5.mp4

### Step 3 — Add POS transactions
Copy your CSV file to:
data/pos_transactions.csv

### Step 4 — Start the API
```bash
docker compose up --build
```
API will be available at: http://localhost:8000

### Step 5 — Run detection pipeline
Open a new terminal:
```bash
cd pipeline
pip install ultralytics opencv-python
python detect.py
```

### Step 6 — Ingest events into API
```bash
python ingest.py
```

---

## Running the Detection Pipeline

```bash
# Run everything in one command (Windows)
cd pipeline
run.bat

# Or run steps separately
python detect.py    # Process videos → generates events
python ingest.py    # Feed events → into API
```

Detection output:
pipeline/events/events_ST1008.jsonl   ← all events
pipeline/events/summary_ST1008.json   ← event summary

---

## API Endpoints

| Endpoint | Description |
|---|---|
| POST /events/ingest | Ingest detection events |
| GET /stores/ST1008/metrics | Store metrics |
| GET /stores/ST1008/funnel | Conversion funnel |
| GET /stores/ST1008/heatmap | Zone heatmap |
| GET /stores/ST1008/anomalies | Active anomalies |
| GET /health | System health |

Full API docs: http://localhost:8000/docs

---

## Running Tests

```bash
cd tests
pip install pytest pytest-asyncio httpx
pytest -v --tb=short
```

---

## Live Dashboard

```bash
cd pipeline
python dashboard.py
```

Shows live metrics updating in terminal as events flow in.

---

## Project Structure
store-intelligence/
├── pipeline/
│   ├── detect.py      ← Main detection script
│   ├── tracker.py     ← Person tracking + Re-ID
│   ├── emit.py        ← Event emission
│   ├── ingest.py      ← Feed events to API
│   ├── dashboard.py   ← Live terminal dashboard
│   └── run.bat        ← One command pipeline (Windows)
├── app/
│   ├── main.py        ← FastAPI entrypoint
│   ├── database.py    ← Database setup
│   ├── models.py      ← Pydantic schemas
│   └── routers/       ← API endpoints
├── tests/             ← Test files
├── docs/              ← DESIGN.md + CHOICES.md
├── data/
│   ├── store_layout.json
│   ├── pos_transactions.csv
│   └── videos/        ← Put video files here
└── docker-compose.yml



## Architecture
CCTV Videos → YOLOv8s Detection → Custom IOU Tracker
→ Event Emitter → JSONL File → FastAPI Ingest
→ SQLite Database → Analytics Endpoints