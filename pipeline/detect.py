import cv2
import json
import os
import sys
import logging
from datetime import datetime, timedelta
from ultralytics import YOLO
from tracker import VisitorTracker
from emit import EventEmitter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

STORE_LAYOUT_PATH = os.getenv(
    "STORE_LAYOUT", "../data/store_layout.json"
)
VIDEO_DIR   = os.getenv("VIDEO_DIR", "../data/videos")
EVENTS_DIR  = os.getenv("EVENTS_DIR", "./events")
FRAME_SKIP  = int(os.getenv("FRAME_SKIP", "3"))
CONF_THRESH = float(os.getenv("CONF_THRESHOLD", "0.4"))

def load_store_layout(path):
    with open(path, "r") as f:
        return json.load(f)

def get_camera_type(camera_id, store):
    for cam in store["cameras"]:
        if cam["camera_id"] == camera_id:
            return cam["type"]
    return "zone"

def get_zone_for_camera(camera_id, store):
    for zone in store["zones"]:
        if camera_id in zone["camera_ids"]:
            return zone["zone_id"]
    return None

def process_video(
    video_path, camera_id, store,
    model, tracker, emitter
):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Cannot open video: {video_path}")
        return

    fps          = cap.get(cv2.CAP_PROP_FPS) or 15
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    camera_type  = get_camera_type(camera_id, store)
    zone_id      = get_zone_for_camera(camera_id, store)
    store_id     = store["store_id"]

    logger.info(
        f"Processing {store_id}/{camera_id} | "
        f"type={camera_type} | fps={fps} | frames={total_frames}"
    )

    # Align with POS transaction window
    base_time = datetime(2026, 4, 10, 12, 0, 0)

    frame_count = 0
    processed   = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        if frame_count % FRAME_SKIP != 0:
            continue

        processed += 1
        seconds_elapsed = frame_count / fps
        current_time = base_time + timedelta(seconds=seconds_elapsed)

        results = model(
            frame,
            classes=[0],
            conf=CONF_THRESH,
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

        tracked_events = tracker.update(
            detections, frame, current_time,
            camera_id, camera_type, zone_id, store_id
        )

        for event_data in tracked_events:
            emitter.emit(event_data)

        if processed % 100 == 0:
            logger.info(
                f"{store_id}/{camera_id}: "
                f"processed {processed} frames "
                f"| detections={len(detections)}"
            )

    cap.release()
    logger.info(f"Finished {store_id}/{camera_id} — {processed} frames")

def process_store(store, model):
    store_id = store["store_id"]
    logger.info(f"=== Processing store: {store_id} ===")

    os.makedirs(EVENTS_DIR, exist_ok=True)
    tracker = VisitorTracker(store)
    emitter = EventEmitter(EVENTS_DIR, store_id)

    for camera in store["cameras"]:
        camera_id  = camera["camera_id"]
        video_file = camera["file"]
        video_path = os.path.join(VIDEO_DIR, video_file)

        if not os.path.exists(video_path):
            logger.warning(f"Video not found: {video_path} — skipping")
            continue

        process_video(video_path, camera_id, store, model, tracker, emitter)

    tracker.finalize(emitter)
    emitter.save()
    logger.info(
        f"Store {store_id} complete — "
        f"total events: {emitter.event_count}"
    )

def main():
    if not os.path.exists(STORE_LAYOUT_PATH):
        logger.error(f"Layout not found: {STORE_LAYOUT_PATH}")
        sys.exit(1)

    layout = load_store_layout(STORE_LAYOUT_PATH)
    stores = layout.get("stores", [layout])  # support both formats

    logger.info("Loading YOLOv8s model...")
    model = YOLO("yolov8s.pt")
    logger.info("YOLOv8s loaded")

    for store in stores:
        process_store(store, model)

    logger.info("All stores processed.")

if __name__ == "__main__":
    main()