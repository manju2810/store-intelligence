from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from database import get_db
from models import MetricsResponse, ZoneDwell
import logging
from datetime import date

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/{store_id}/metrics", response_model=MetricsResponse)
async def get_metrics(store_id: str, db: AsyncSession = Depends(get_db)):
    try:
        today = date.today().isoformat()

        # ── Unique visitors ──────────────────────────────
        visitors_result = await db.execute(
            text("""
                SELECT COUNT(DISTINCT visitor_id)
                FROM events
                WHERE store_id = :store_id
                AND is_staff = 0
                AND event_type IN ('ENTRY', 'REENTRY')
            """),
            {"store_id": store_id}
        )
        unique_visitors = visitors_result.scalar() or 0

        # ── Conversion rate (5 min window) ───────────────
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
                    ) <= 1800
                )
            """),
            {"store_id": store_id}
        )
        converted_visitors = converted_result.scalar() or 0

        if unique_visitors > 0:
            converted_visitors = min(converted_visitors, unique_visitors)
            conversion_rate = round(
                converted_visitors / unique_visitors * 100, 2
            )
        else:
            conversion_rate = 0.0

        # ── Avg dwell per zone ───────────────────────────
        dwell_result = await db.execute(
            text("""
                SELECT zone_id,
                       COUNT(*) as visit_count,
                       AVG(dwell_ms) as avg_dwell
                FROM events
                WHERE store_id = :store_id
                AND is_staff = 0
                AND event_type = 'ZONE_DWELL'
                AND zone_id IS NOT NULL
                GROUP BY zone_id
            """),
            {"store_id": store_id}
        )
        dwell_rows = dwell_result.fetchall()

        avg_dwell_per_zone = [
            ZoneDwell(
                zone_id=row[0],
                zone_name=row[0].replace("_", " ").title(),
                avg_dwell_seconds=round((row[2] or 0) / 1000, 2),
                visit_count=row[1]
            )
            for row in dwell_rows
        ]

        # ── Queue depth ──────────────────────────────────
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
        queue_depth = queue_result.scalar() or 0

        # ── Abandonment rate ─────────────────────────────
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
            round(abandoned / queue_joins * 100, 2)
            if queue_joins > 0 else 0.0
        )

        logger.info(
            f"store_id={store_id} "
            f"unique_visitors={unique_visitors} "
            f"converted={converted_visitors} "
            f"conversion_rate={conversion_rate}"
        )

        return MetricsResponse(
            store_id=store_id,
            date=today,
            unique_visitors=unique_visitors,
            conversion_rate=conversion_rate,
            avg_dwell_per_zone=avg_dwell_per_zone,
            queue_depth=queue_depth,
            abandonment_rate=abandonment_rate
        )

    except Exception as e:
        logger.error(f"Metrics error for {store_id}: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Service unavailable",
                "detail": str(e)
            }
        )