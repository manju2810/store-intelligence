import json
import requests
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ── Config ───────────────────────────────────────────────
API_URL    = os.getenv("API_URL", "http://localhost:8000")
EVENTS_DIR = os.getenv("EVENTS_DIR", "./events")
BATCH_SIZE = 500  # Max events per API call

def load_events(events_file):
    """Load events from JSONL file"""
    events = []
    with open(events_file, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON line: {e}")
    return events

def ingest_batch(events):
    """Send a batch of events to the API"""
    try:
        # Convert to API format
        formatted = []
        for e in events:
            formatted.append({
                "event_id"  : e["event_id"],
                "store_id"  : e["store_id"],
                "camera_id" : e["camera_id"],
                "visitor_id": e["visitor_id"],
                "event_type": e["event_type"],
                "timestamp" : e["timestamp"],
                "zone_id"   : e.get("zone_id"),
                "dwell_ms"  : e.get("dwell_ms", 0),
                "is_staff"  : e.get("is_staff", False),
                "confidence": e.get("confidence", 0.9),
                "metadata"  : e.get("metadata", {
                    "queue_depth": None,
                    "sku_zone"   : None,
                    "session_seq": 0
                })
            })

        response = requests.post(
            f"{API_URL}/events/ingest",
            json={"events": formatted},
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            logger.info(
                f"Batch ingested: "
                f"accepted={result['accepted']} "
                f"rejected={result['rejected']} "
                f"duplicate={result['duplicate']}"
            )
            return True
        else:
            logger.error(
                f"Ingest failed: "
                f"status={response.status_code} "
                f"body={response.text}"
            )
            return False

    except requests.exceptions.ConnectionError:
        logger.error(
            "Cannot connect to API. "
            "Make sure docker compose up is running."
        )
        return False
    except Exception as e:
        logger.error(f"Ingest error: {e}")
        return False

def wait_for_api(max_retries=10):
    """Wait for API to be ready"""
    logger.info("Waiting for API to be ready...")
    for i in range(max_retries):
        try:
            response = requests.get(
                f"{API_URL}/health",
                timeout=5
            )
            if response.status_code == 200:
                logger.info("API is ready")
                return True
        except Exception:
            pass
        logger.info(f"Retry {i+1}/{max_retries}...")
        time.sleep(3)
    return False

def main():
    # Wait for API
    if not wait_for_api():
        logger.error("API not available. Exiting.")
        return

    # Find events files
    events_dir = Path(EVENTS_DIR)
    event_files = list(events_dir.glob("events_*.jsonl"))

    if not event_files:
        logger.error(f"No event files found in {EVENTS_DIR}")
        return

    total_ingested = 0

    for events_file in event_files:
        logger.info(f"Processing: {events_file}")

        # Load all events
        events = load_events(events_file)
        logger.info(f"Loaded {len(events)} events")

        if not events:
            continue

        # Send in batches of 500
        for i in range(0, len(events), BATCH_SIZE):
            batch = events[i:i + BATCH_SIZE]
            logger.info(
                f"Sending batch "
                f"{i//BATCH_SIZE + 1} "
                f"({len(batch)} events)"
            )
            success = ingest_batch(batch)
            if not success:
                logger.error("Batch failed — stopping")
                break
            total_ingested += len(batch)
            time.sleep(0.5)  # Small delay between batches

    logger.info(
        f"Ingest complete. "
        f"Total events ingested: {total_ingested}"
    )

if __name__ == "__main__":
    main()