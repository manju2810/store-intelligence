import uuid
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

REENTRY_WINDOW_SECONDS = 300
STAFF_ZONE_THRESHOLD   = 4
STAFF_TIME_THRESHOLD   = 600
DWELL_EMIT_SECONDS     = 30
IOU_THRESHOLD          = 0.3
MAX_DISAPPEARED        = 30

class Track:
    def __init__(self, track_id, bbox, confidence, timestamp):
        self.track_id        = track_id
        self.visitor_id      = f"VIS_{uuid.uuid4().hex[:6]}"
        self.bbox            = bbox
        self.confidence      = confidence
        self.first_seen      = timestamp
        self.last_seen       = timestamp
        self.disappeared     = 0
        self.zones_visited   = set()
        self.current_zone    = None
        self.zone_enter_time = None
        self.last_dwell_emit = None
        self.is_staff        = False
        self.staff_score     = 0
        self.session_seq     = 0
        self.entry_emitted   = False
        self.exit_emitted    = False
        self.billing_joined  = False

    def update(self, bbox, confidence, timestamp):
        self.bbox        = bbox
        self.confidence  = confidence
        self.last_seen   = timestamp
        self.disappeared = 0

class VisitorTracker:
    def __init__(self, store):
        self.store           = store
        self.tracks          = {}
        self.next_track_id   = 1
        self.exited_visitors = {}
        self.pending_events  = []

    def _iou(self, b1, b2):
        x1 = max(b1[0], b2[0])
        y1 = max(b1[1], b2[1])
        x2 = min(b1[2], b2[2])
        y2 = min(b1[3], b2[3])
        inter = max(0, x2-x1) * max(0, y2-y1)
        if inter == 0:
            return 0.0
        a1 = (b1[2]-b1[0]) * (b1[3]-b1[1])
        a2 = (b2[2]-b2[0]) * (b2[3]-b2[1])
        return inter / (a1 + a2 - inter)

    def _check_staff(self, track):
        score = 0
        if len(track.zones_visited) >= STAFF_ZONE_THRESHOLD:
            score += 3
        duration = (track.last_seen - track.first_seen).total_seconds()
        if duration > STAFF_TIME_THRESHOLD:
            score += 3
        if len(track.zones_visited) > 2 and not track.billing_joined:
            score += 2
        if duration > 1800:
            score += 2
        track.staff_score = score
        if score >= 5:
            track.is_staff = True
        return track.is_staff

    def _get_zone(self, camera_id):
        for zone in self.store["zones"]:
            if camera_id in zone["camera_ids"]:
                return zone["zone_id"]
        return None

    def _get_sku_zone(self, zone_id):
        for zone in self.store["zones"]:
            if zone["zone_id"] == zone_id:
                return zone.get("sku_zone")
        return None

    def _check_reentry(self, bbox, timestamp):
        for visitor_id, data in self.exited_visitors.items():
            diff = (timestamp - data["exit_time"]).total_seconds()
            if diff > REENTRY_WINDOW_SECONDS:
                continue
            if data["exit_bbox"]:
                if self._iou(bbox, data["exit_bbox"]) > 0.2:
                    return visitor_id
        return None

    def _get_queue_depth(self):
        return sum(
            1 for t in self.tracks.values()
            if t.current_zone == "BILLING" and not t.is_staff
        )

    def update(self, detections, frame, timestamp,
               camera_id, camera_type, zone_id, store_id):
        events  = []
        matched = set()
        unmatched = []

        # Match detections to existing tracks
        for det in detections:
            best_iou, best_track = IOU_THRESHOLD, None
            for tid, track in self.tracks.items():
                iou = self._iou(det["bbox"], track.bbox)
                if iou > best_iou:
                    best_iou, best_track = iou, tid
            if best_track is not None:
                self.tracks[best_track].update(
                    det["bbox"], det["confidence"], timestamp
                )
                matched.add(best_track)
            else:
                unmatched.append(det)

        # New tracks
        for det in unmatched:
            reentry_id = self._check_reentry(det["bbox"], timestamp)
            track = Track(
                self.next_track_id,
                det["bbox"],
                det["confidence"],
                timestamp
            )
            if reentry_id:
                track.visitor_id = reentry_id
                event_type = "REENTRY"
                del self.exited_visitors[reentry_id]
            else:
                event_type = "ENTRY"

            self.tracks[self.next_track_id] = track
            self.next_track_id += 1

            if camera_type == "entry" and not track.entry_emitted:
                track.entry_emitted = True
                track.session_seq += 1
                events.append({
                    "track": track, "event_type": event_type,
                    "timestamp": timestamp, "camera_id": camera_id,
                    "zone_id": None, "store_id": store_id,
                    "dwell_ms": 0, "queue_depth": None
                })

        # Zone tracking for matched tracks
        for tid in matched:
            track = self.tracks[tid]
            current_zone = self._get_zone(camera_id)

            if current_zone and current_zone != track.current_zone:
                # Emit ZONE_EXIT for previous zone
                if track.current_zone:
                    dwell_ms = 0
                    if track.zone_enter_time:
                        dwell_ms = int((
                            timestamp - track.zone_enter_time
                        ).total_seconds() * 1000)
                    track.session_seq += 1
                    events.append({
                        "track": track, "event_type": "ZONE_EXIT",
                        "timestamp": timestamp, "camera_id": camera_id,
                        "zone_id": track.current_zone,
                        "store_id": store_id,
                        "dwell_ms": dwell_ms, "queue_depth": None
                    })

                track.current_zone    = current_zone
                track.zone_enter_time = timestamp
                track.last_dwell_emit = timestamp
                track.zones_visited.add(current_zone)
                track.session_seq += 1

                if current_zone == "BILLING":
                    queue_depth = self._get_queue_depth()
                    track.billing_joined = True
                    evt = "BILLING_QUEUE_JOIN" if queue_depth > 0 else "ZONE_ENTER"
                    events.append({
                        "track": track, "event_type": evt,
                        "timestamp": timestamp, "camera_id": camera_id,
                        "zone_id": current_zone, "store_id": store_id,
                        "dwell_ms": 0, "queue_depth": queue_depth
                    })
                else:
                    events.append({
                        "track": track, "event_type": "ZONE_ENTER",
                        "timestamp": timestamp, "camera_id": camera_id,
                        "zone_id": current_zone, "store_id": store_id,
                        "dwell_ms": 0, "queue_depth": None
                    })

            # ZONE_DWELL every 30 seconds
            if (track.current_zone and track.last_dwell_emit and
                (timestamp - track.last_dwell_emit
                 ).total_seconds() >= DWELL_EMIT_SECONDS):
                track.last_dwell_emit = timestamp
                track.session_seq += 1
                events.append({
                    "track": track, "event_type": "ZONE_DWELL",
                    "timestamp": timestamp, "camera_id": camera_id,
                    "zone_id": track.current_zone, "store_id": store_id,
                    "dwell_ms": DWELL_EMIT_SECONDS * 1000,
                    "queue_depth": None
                })

        # Disappeared tracks
        for tid in list(self.tracks.keys()):
            if tid not in matched:
                self.tracks[tid].disappeared += 1
                if self.tracks[tid].disappeared > MAX_DISAPPEARED:
                    track = self.tracks[tid]
                    self._check_staff(track)

                    if camera_type == "entry" and not track.exit_emitted:
                        track.exit_emitted = True

                        if track.billing_joined and track.current_zone == "BILLING":
                            track.session_seq += 1
                            events.append({
                                "track": track,
                                "event_type": "BILLING_QUEUE_ABANDON",
                                "timestamp": timestamp,
                                "camera_id": camera_id,
                                "zone_id": "BILLING",
                                "store_id": store_id,
                                "dwell_ms": 0, "queue_depth": None
                            })

                        track.session_seq += 1
                        events.append({
                            "track": track, "event_type": "EXIT",
                            "timestamp": timestamp, "camera_id": camera_id,
                            "zone_id": None, "store_id": store_id,
                            "dwell_ms": 0, "queue_depth": None
                        })
                        self.exited_visitors[track.visitor_id] = {
                            "exit_time": timestamp,
                            "exit_bbox": track.bbox
                        }

                    del self.tracks[tid]

        self.pending_events.extend(events)
        return events

    def finalize(self, emitter):
        now = datetime.utcnow()
        for tid, track in self.tracks.items():
            if not track.exit_emitted:
                self._check_staff(track)
                emitter.emit({
                    "track": track, "event_type": "EXIT",
                    "timestamp": now,
                    "camera_id": self.store["cameras"][0]["camera_id"],
                    "zone_id": None,
                    "store_id": self.store["store_id"],
                    "dwell_ms": 0, "queue_depth": None
                })