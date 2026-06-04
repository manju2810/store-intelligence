from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from database import get_db
from models import FunnelResponse, FunnelStage
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/{store_id}/funnel", response_model=FunnelResponse)
async def get_funnel(store_id: str, db: AsyncSession = Depends(get_db)):
    try:

        # ── Stage 1: Entry visitors ─────────────────────
        entry_result = await db.execute(
            text("""
                SELECT COUNT(DISTINCT visitor_id)
                FROM events
                WHERE store_id = :store_id
                AND is_staff = 0
                AND event_type IN ('ENTRY', 'REENTRY')
            """),
            {"store_id": store_id}
        )
        total_entries = entry_result.scalar() or 0

        # ── Stage 2: Zone engagement (excluding system zones) ─
        zone_result = await db.execute(
            text("""
                SELECT COUNT(DISTINCT visitor_id)
                FROM events
                WHERE store_id = :store_id
                AND is_staff = 0
                AND event_type IN ('ZONE_ENTER', 'ZONE_DWELL')
                AND zone_id IS NOT NULL
                AND zone_id NOT IN ('ENTRY', 'EXIT', 'BILLING')
            """),
            {"store_id": store_id}
        )
        zone_visitors = zone_result.scalar() or 0

        # ── Stage 3: Billing visitors (consistent definition) ─
        billing_result = await db.execute(
            text("""
                SELECT COUNT(DISTINCT visitor_id)
                FROM events
                WHERE store_id = :store_id
                AND is_staff = 0
                AND zone_id = 'BILLING'
                AND event_type IN ('ZONE_ENTER', 'BILLING_QUEUE_JOIN')
            """),
            {"store_id": store_id}
        )
        billing_visitors = billing_result.scalar() or 0

        # ── Stage 4: Purchases (proper visitor match) ─
        purchase_result = await db.execute(
            text("""
                SELECT COUNT(DISTINCT e.visitor_id)
                FROM events e
                WHERE e.store_id = :store_id
                AND e.is_staff = 0
                AND e.zone_id = 'BILLING'
                AND EXISTS (
                    SELECT 1
                    FROM pos_transactions p
                    WHERE p.store_id = e.store_id
                    AND p.visitor_id = e.visitor_id
                    AND ABS(
                        strftime('%s', e.timestamp) -
                        strftime('%s', p.timestamp)
                    ) <= 1800
                )
            """),
            {"store_id": store_id}
        )
        purchases = purchase_result.scalar() or 0

        # ── Safe drop-off calculation ─
        def drop_off(curr, prev):
            if prev <= 0:
                return None
            return round((1 - curr / prev) * 100, 2)

        stages = [
            FunnelStage(
                stage="Entry",
                count=total_entries,
                drop_off_pct=0.0
            ),
            FunnelStage(
                stage="Zone Visit",
                count=zone_visitors,
                drop_off_pct=drop_off(zone_visitors, total_entries)
            ),
            FunnelStage(
                stage="Billing",
                count=billing_visitors,
                drop_off_pct=drop_off(billing_visitors, zone_visitors)
            ),
            FunnelStage(
                stage="Purchase",
                count=purchases,
                drop_off_pct=drop_off(purchases, billing_visitors)
            )
        ]

        logger.info(
            f"store_id={store_id} "
            f"entry={total_entries} "
            f"zone={zone_visitors} "
            f"billing={billing_visitors} "
            f"purchase={purchases}"
        )

        return FunnelResponse(
            store_id=store_id,
            stages=stages
        )

    except Exception as e:
        logger.error(f"Funnel error for {store_id}: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Service unavailable",
                "detail": str(e)
            }
        )