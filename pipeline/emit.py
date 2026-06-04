import json
import uuid
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class EventEmitter:
    def __init__(self, events_dir, store_id):
        self.events_dir  = events_dir
        self.store_id    = store_id
        self.events      = []
        self.event_count = 0
        os.makedirs(events_dir, exist_ok=True)

    def emit(self, event_data):
        try:
            track     = event_data["track"]
            timestamp = event_data["timestamp"]

            if isinstance(timestamp, datetime):
                timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                timestamp_str = str(timestamp)

            zone_id  = event_data.get("zone_id")
            sku_zone = self._get_sku_zone(zone_id)

            event = {
                "event_id"  : str(uuid.uuid4()),
                "store_id"  : event_data["store_id"],
                "camera_id" : event_data["camera_id"],
                "visitor_id": track.visitor_id,
                "event_type": event_data["event_type"],
                "timestamp" : timestamp_str,
                "zone_id"   : zone_id,
                "dwell_ms"  : event_data.get("dwell_ms", 0),
                "is_staff"  : track.is_staff,
                "confidence": round(track.confidence, 2),
                "metadata"  : {
                    "queue_depth": event_data.get("queue_depth"),
                    "sku_zone"   : sku_zone,
                    "session_seq": track.session_seq
                }
            }

            self.events.append(event)
            self.event_count += 1

            if self.event_count % 50 == 0:
                logger.info(f"Emitted {self.event_count} events")

            return event

        except Exception as e:
            logger.error(f"Failed to emit event: {e}")
            return None

    def _get_sku_zone(self, zone_id):
        if not zone_id:
            return None
        try:
            layout_path = os.getenv(
                "STORE_LAYOUT", "../data/store_layout.json"
            )
            with open(layout_path) as f:
                layout = json.load(f)
            stores = layout.get("stores", [layout])
            for store in stores:
                if store["store_id"] == self.store_id:
                    for zone in store["zones"]:
                        if zone["zone_id"] == zone_id:
                            return zone.get("sku_zone")
        except Exception:
            pass
        return None

    def save(self):
        if not self.events:
            logger.warning("No events to save")
            return

        output_path = os.path.join(
            self.events_dir,
            f"events_{self.store_id}.jsonl"
        )
        with open(output_path, "w") as f:
            for event in self.events:
                f.write(json.dumps(event) + "\n")

        logger.info(
            f"Saved {self.event_count} events to {output_path}"
        )
        self._save_summary()

    def _save_summary(self):
        summary = {
            "store_id"    : self.store_id,
            "total_events": self.event_count,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "event_types" : {}
        }
        for event in self.events:
            et = event["event_type"]
            summary["event_types"][et] = (
                summary["event_types"].get(et, 0) + 1
            )

        summary_path = os.path.join(
            self.events_dir,
            f"summary_{self.store_id}.json"
        )
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Summary: {summary['event_types']}")