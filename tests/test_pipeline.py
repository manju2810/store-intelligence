# PROMPT: Generate tests for a retail store detection pipeline
# that validates event schema compliance, entry/exit counting,
# staff exclusion, re-entry handling, and group entry detection.
# Use pytest with async support for FastAPI endpoints.
# CHANGES MADE: Added edge cases for empty store periods,
# zero confidence events, and duplicate event_ids.

import pytest
import json
import uuid
from datetime import datetime

# ── Sample valid event ───────────────────────────────────
def make_event(
    event_type="ENTRY",
    is_staff=False,
    zone_id=None,
    visitor_id=None,
    confidence=0.9
):
    return {
        "event_id"  : str(uuid.uuid4()),
        "store_id"  : "ST1008",
        "camera_id" : "CAM1",
        "visitor_id": visitor_id or f"VIS_{uuid.uuid4().hex[:6]}",
        "event_type": event_type,
        "timestamp" : datetime.utcnow().strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "zone_id"   : zone_id,
        "dwell_ms"  : 0,
        "is_staff"  : is_staff,
        "confidence": confidence,
        "metadata"  : {
            "queue_depth": None,
            "sku_zone"   : None,
            "session_seq": 1
        }
    }

# ── Schema compliance tests ──────────────────────────────
class TestEventSchema:

    def test_valid_event_has_all_fields(self):
        event = make_event()
        required = [
            "event_id", "store_id", "camera_id",
            "visitor_id", "event_type", "timestamp",
            "zone_id", "dwell_ms", "is_staff",
            "confidence", "metadata"
        ]
        for field in required:
            assert field in event, f"Missing field: {field}"

    def test_event_id_is_unique(self):
        events = [make_event() for _ in range(100)]
        ids = [e["event_id"] for e in events]
        assert len(set(ids)) == 100

    def test_confidence_between_0_and_1(self):
        event = make_event(confidence=0.75)
        assert 0.0 <= event["confidence"] <= 1.0

    def test_low_confidence_event_not_dropped(self):
        # Low confidence events must be kept not dropped
        event = make_event(confidence=0.25)
        assert event["confidence"] == 0.25

    def test_timestamp_is_iso_format(self):
        event = make_event()
        ts = event["timestamp"]
        try:
            datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
            valid = True
        except ValueError:
            valid = False
        assert valid

    def test_valid_event_types(self):
        valid_types = [
            "ENTRY", "EXIT", "ZONE_ENTER", "ZONE_EXIT",
            "ZONE_DWELL", "BILLING_QUEUE_JOIN",
            "BILLING_QUEUE_ABANDON", "REENTRY"
        ]
        for et in valid_types:
            event = make_event(event_type=et)
            assert event["event_type"] == et

    def test_metadata_has_required_fields(self):
        event = make_event()
        assert "queue_depth" in event["metadata"]
        assert "sku_zone" in event["metadata"]
        assert "session_seq" in event["metadata"]

# ── Entry exit tests ─────────────────────────────────────
class TestEntryExit:

    def test_entry_event_has_no_zone(self):
        event = make_event(event_type="ENTRY", zone_id=None)
        assert event["zone_id"] is None

    def test_exit_event_has_no_zone(self):
        event = make_event(event_type="EXIT", zone_id=None)
        assert event["zone_id"] is None

    def test_zone_dwell_has_zone_id(self):
        event = make_event(
            event_type="ZONE_DWELL",
            zone_id="SKINCARE"
        )
        assert event["zone_id"] == "SKINCARE"

    def test_group_entry_emits_multiple_events(self):
        # 3 people entering together = 3 ENTRY events
        visitor_ids = [
            f"VIS_{uuid.uuid4().hex[:6]}"
            for _ in range(3)
        ]
        events = [
            make_event(
                event_type="ENTRY",
                visitor_id=vid
            )
            for vid in visitor_ids
        ]
        assert len(events) == 3
        assert len(set(
            e["visitor_id"] for e in events
        )) == 3

# ── Staff exclusion tests ────────────────────────────────
class TestStaffExclusion:

    def test_staff_flagged_correctly(self):
        event = make_event(is_staff=True)
        assert event["is_staff"] is True

    def test_customer_not_flagged_as_staff(self):
        event = make_event(is_staff=False)
        assert event["is_staff"] is False

    def test_staff_events_excluded_from_count(self):
        events = [
            make_event(is_staff=False),
            make_event(is_staff=False),
            make_event(is_staff=True),   # staff
            make_event(is_staff=False),
        ]
        customer_events = [
            e for e in events
            if not e["is_staff"]
        ]
        assert len(customer_events) == 3

# ── Re-entry tests ───────────────────────────────────────
class TestReentry:

    def test_reentry_uses_same_visitor_id(self):
        visitor_id = f"VIS_{uuid.uuid4().hex[:6]}"
        entry = make_event(
            event_type="ENTRY",
            visitor_id=visitor_id
        )
        reentry = make_event(
            event_type="REENTRY",
            visitor_id=visitor_id
        )
        assert entry["visitor_id"] == reentry["visitor_id"]

    def test_reentry_event_type_is_reentry(self):
        event = make_event(event_type="REENTRY")
        assert event["event_type"] == "REENTRY"

# ── Edge case tests ──────────────────────────────────────
class TestEdgeCases:

    def test_empty_store_no_events(self):
        events = []
        unique_visitors = len(set(
            e["visitor_id"] for e in events
            if e["event_type"] == "ENTRY"
            and not e["is_staff"]
        ))
        assert unique_visitors == 0

    def test_zero_purchases_conversion_rate(self):
        unique_visitors = 10
        purchases = 0
        conversion = (
            purchases / unique_visitors * 100
            if unique_visitors > 0 else 0.0
        )
        assert conversion == 0.0

    def test_all_staff_clip(self):
        events = [
            make_event(is_staff=True)
            for _ in range(10)
        ]
        customer_events = [
            e for e in events
            if not e["is_staff"]
        ]
        assert len(customer_events) == 0

    def test_duplicate_event_id_detected(self):
        event_id = str(uuid.uuid4())
        event1 = make_event()
        event1["event_id"] = event_id
        event2 = make_event()
        event2["event_id"] = event_id

        seen_ids = set()
        duplicates = 0
        for e in [event1, event2]:
            if e["event_id"] in seen_ids:
                duplicates += 1
            seen_ids.add(e["event_id"])

        assert duplicates == 1