from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from database import get_db
from models import AnomalyResponse, Anomaly
import logging
import uuid
from datetime import datetime, timedelta

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/{store_id}/anomalies", response_model=AnomalyResponse)
async def get_anomalies(store_id: str, db: AsyncSession = Depends(get_db)):
    try:
        anomalies = []
        now = datetime.utcnow()

        # ── Anomaly 1: Queue Spike ───────────────────────
        queue_result = await db.execute(
            text("""
                SELECT MAX(queue_depth)
                FROM events
                WHERE store_id = :store_id
                AND event_type = 'BILLING_QUEUE_JOIN'
                AND queue_depth IS NOT NULL
            """),
            {"store_id": store_id}
        )
        max_queue = queue_result.scalar() or 0

        if max_queue >= 5:
            anomalies.append(Anomaly(
                anomaly_id=str(uuid.uuid4()),
                anomaly_type="BILLING_QUEUE_SPIKE",
                severity="CRITICAL" if max_queue >= 8 else "WARN",
                description=f"Queue depth reached {max_queue} at billing counter",
                suggested_action="Deploy additional staff to billing counter immediately",
                detected_at=now.isoformat() + "Z"
            ))

        # ── Anomaly 2: Conversion Drop ───────────────────
        # Compare current conversion to average
        total_visitors_result = await db.execute(
            text("""
                SELECT COUNT(DISTINCT visitor_id)
                FROM events
                WHERE store_id = :store_id
                AND is_staff = 0
                AND event_type IN ('ENTRY', 'REENTRY')
            """),
            {"store_id": store_id}
        )
        total_visitors = total_visitors_result.scalar() or 0

        converted_result = await db.execute(
            text("""
                SELECT COUNT(DISTINCT e.visitor_id)
                FROM events e
                WHERE e.store_id = :store_id
                AND e.is_staff = 0
                AND e.zone_id = 'BILLING'
                AND EXISTS (
                    SELECT 1 FROM pos_transactions p
                    WHERE p.store_id = :store_id
                    AND ABS(
                        strftime('%s', e.timestamp) -
                        strftime('%s', p.timestamp)
                    ) <= 300
                )
            """),
            {"store_id": store_id}
        )
        converted = converted_result.scalar() or 0

        current_conversion = (
            converted / total_visitors * 100
            if total_visitors > 0 else 0
        )

        # Flag if conversion is below 10%
        if total_visitors > 10 and current_conversion < 10.0:
            anomalies.append(Anomaly(
                anomaly_id=str(uuid.uuid4()),
                anomaly_type="CONVERSION_DROP",
                severity="WARN",
                description=(
                    f"Conversion rate is {round(current_conversion, 2)}% "
                    f"which is below the 10% threshold"
                ),
                suggested_action=(
                    "Review product placement and staff engagement. "
                    "Check if billing counter is understaffed."
                ),
                detected_at=now.isoformat() + "Z"
            ))

        # ── Anomaly 3: Dead Zone ─────────────────────────
        # Zone with no visits in last 30 minutes
        thirty_min_ago = (
            now - timedelta(minutes=30)
        ).isoformat() + "Z"

        active_zones_result = await db.execute(
            text("""
                SELECT DISTINCT zone_id
                FROM events
                WHERE store_id = :store_id
                AND is_staff = 0
                AND zone_id IS NOT NULL
                AND timestamp >= :thirty_min_ago
            """),
            {
                "store_id": store_id,
                "thirty_min_ago": thirty_min_ago
            }
        )
        active_zones = [
            row[0] for row in active_zones_result.fetchall()
        ]

        # Get all zones that have ever had visits
        all_zones_result = await db.execute(
            text("""
                SELECT DISTINCT zone_id
                FROM events
                WHERE store_id = :store_id
                AND is_staff = 0
                AND zone_id IS NOT NULL
                AND zone_id NOT IN ('ENTRY', 'EXIT')
            """),
            {"store_id": store_id}
        )
        all_zones = [
            row[0] for row in all_zones_result.fetchall()
        ]

        dead_zones = [
            z for z in all_zones
            if z not in active_zones
        ]

        for zone in dead_zones:
            anomalies.append(Anomaly(
                anomaly_id=str(uuid.uuid4()),
                anomaly_type="DEAD_ZONE",
                severity="INFO",
                description=(
                    f"Zone {zone} has had no visitor activity "
                    f"in the last 30 minutes"
                ),
                suggested_action=(
                    f"Check if {zone} zone display is attractive. "
                    f"Consider repositioning products or adding promotions."
                ),
                detected_at=now.isoformat() + "Z"
            ))

        # ── Anomaly 4: High Abandonment ──────────────────
        abandon_result = await db.execute(
            text("""
                SELECT COUNT(DISTINCT visitor_id)
                FROM events
                WHERE store_id = :store_id
                AND is_staff = 0
                AND event_type = 'BILLING_QUEUE_ABANDON'
            """),
            {"store_id": store_id}
        )
        abandoned = abandon_result.scalar() or 0

        queue_joins_result = await db.execute(
            text("""
                SELECT COUNT(DISTINCT visitor_id)
                FROM events
                WHERE store_id = :store_id
                AND is_staff = 0
                AND event_type = 'BILLING_QUEUE_JOIN'
            """),
            {"store_id": store_id}
        )
        queue_joins = queue_joins_result.scalar() or 0

        abandonment_rate = (
            abandoned / queue_joins * 100
            if queue_joins > 0 else 0
        )

        if abandonment_rate >= 30:
            anomalies.append(Anomaly(
                anomaly_id=str(uuid.uuid4()),
                anomaly_type="HIGH_ABANDONMENT",
                severity="CRITICAL" if abandonment_rate >= 50 else "WARN",
                description=(
                    f"Billing queue abandonment rate is "
                    f"{round(abandonment_rate, 2)}%"
                ),
                suggested_action=(
                    "Open additional billing counter. "
                    "Deploy staff to assist customers in queue."
                ),
                detected_at=now.isoformat() + "Z"
            ))

        logger.info(
            f"store_id={store_id} "
            f"anomalies_detected={len(anomalies)}"
        )

        return AnomalyResponse(
            store_id=store_id,
            anomalies=anomalies
        )

    except Exception as e:
        logger.error(f"Anomalies error for {store_id}: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Service unavailable",
                "detail": str(e)
            }
        )