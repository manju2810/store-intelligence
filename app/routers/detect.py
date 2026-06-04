import cv2
import json
import uuid
import os
import sys
import logging
from datetime import datetime, timedelta
from ultralytics import YOLO
from tracker import VisitorTracker
from emit import EventEmitter

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────
STORE_LAYOUT_PATH = os.getenv(
    "STORE_LAYOUT", "../data/store_layout.json"
)
VIDEO_DIR = os.getenv("VIDEO_DIR", "../data/videos")
EVENTS_DIR = os.getenv("EVENTS_DIR", "../pipeline/events")
FRAME_SKIP = int(os.getenv("FRAME_SKIP", "3"))  # Process every 3rd frame
CONFIDENCE_THRESHOLD = float(os.getenv("CONF_THRESHOLD", "0.4"))

def load_store_layout(path):
    with open(path, "r") as f:
        return json.load(f)

def get_camera_type(camera_id, layout):
    for cam in layout["cameras"]:
        if cam["camera_id"] == camera_id:
            return cam["type"]
    return "floor"

def get_zone_for_camera(camera_id, layout):
    for zone in layout["zones"]:
        if camera_id in zone["camera_ids"]:
            return zone["zone_id"]
    return None

def process_video(video_path, camera_id, layout, model, tracker, emitter):
    """Process a single video file and emit events"""

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Cannot open video: {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 15
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    camera_type = get_camera_type(camera_id, layout)
    zone_id = get_zone_for_camera(camera_id, layout)
    store_id = layout["store_id"]

    logger.info(
        f"Processing {camera_id} | "
        f"type={camera_type} | "
        f"fps={fps} | "
        f"frames={total_frames}"
    )

    # Base timestamp — use today with store open time
    base_time = datetime(2026, 4, 10, 12, 0, 0)
    frame_count = 0
    processed = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1

        # Skip frames for performance
        if frame_count % FRAME_SKIP != 0:
            continue

        processed += 1

        # Current timestamp based on frame position
        seconds_elapsed = frame_count / fps
        current_time = base_time + timedelta(seconds=seconds_elapsed)

        # ── Run YOLOv8 detection ─────────────────────────
        results = model(
            frame,
            classes=[0],  # class 0 = person
            conf=CONFIDENCE_THRESHOLD,
            verbose=False
        )

        detections = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                detections.append({
                    "bbox": [x1, y1, x2, y2],
                    "confidence": conf
                })

        # ── Update tracker ───────────────────────────────
        tracked_persons = tracker.update(
            detections,
            frame,
            current_time,
            camera_id,
            camera_type,
            zone_id,
            store_id
        )

        # ── Emit events ──────────────────────────────────
        for person in tracked_persons:
            emitter.emit(person)

        if processed % 100 == 0:
            logger.info(
                f"{camera_id}: processed {processed} frames "
                f"| detections={len(detections)}"
            )

    cap.release()
    logger.info(f"Finished processing {camera_id}")

def main():
    # Load store layout
    layout = load_store_layout(STORE_LAYOUT_PATH)
    logger.info(f"Loaded layout for store: {layout['store_id']}")

    # Load YOLOv8 model
    logger.info("Loading YOLOv8s model...")
    model = YOLO("yolov8s.pt")  # Downloads automatically
    logger.info("YOLOv8s model loaded")

    # Create events output directory
    os.makedirs(EVENTS_DIR, exist_ok=True)

    # Initialize tracker and emitter
    tracker = VisitorTracker(layout)
    emitter = EventEmitter(EVENTS_DIR, layout["store_id"])

    # Process each camera video
    for camera in layout["cameras"]:
        camera_id = camera["camera_id"]
        video_file = camera["file"]
        video_path = os.path.join(VIDEO_DIR, video_file)

        if not os.path.exists(video_path):
            logger.warning(f"Video not found: {video_path}")
            continue

        process_video(
            video_path,
            camera_id,
            layout,
            model,
            tracker,
            emitter
        )

    # Finalize — emit EXIT events for anyone still in store
    tracker.finalize(emitter)

    # Save all events
    emitter.save()
    logger.info(
        f"Detection complete. "
        f"Total events: {emitter.event_count}"
    )

if __name__ == "__main__":
    main()