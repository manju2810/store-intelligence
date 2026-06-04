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
        # ── Stage 1: Total unique visitors ───────────────
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

        # ── Stage 2: Visitors who visited any zone ───────
        zone_result = await db.execute(
            text("""
                SELECT COUNT(DISTINCT visitor_id)
                FROM events
                WHERE store_id = :store_id
                AND is_staff = 0
                AND event_type IN ('ZONE_ENTER', 'ZONE_DWELL')
                AND zone_id NOT IN ('ENTRY', 'EXIT', 'BILLING')
            """),
            {"store_id": store_id}
        )
        zone_visitors = zone_result.scalar() or 0

        # ── Stage 3: Visitors who reached billing ────────
        billing_result = await db.execute(
            text("""
                SELECT COUNT(DISTINCT visitor_id)
                FROM events
                WHERE store_id = :store_id
                AND is_staff = 0
                AND event_type IN (
                    'BILLING_QUEUE_JOIN',
                    'ZONE_ENTER'
                )
                AND zone_id = 'BILLING'
            """),
            {"store_id": store_id}
        )
        billing_visitors = billing_result.scalar() or 0

        # ── Stage 4: Purchases ───────────────────────────
        purchase_result = await db.execute(
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
        purchases = purchase_result.scalar() or 0

        # ── Drop off calculation ─────────────────────────
        def drop_off(current, previous):
            if previous == 0:
                return 0.0
            return round((1 - current / previous) * 100, 2)

        stages = [
            FunnelStage(
                stage="Entry",
                count=total_entries,
                drop_off_pct=0.0
            ),
            FunnelStage(
                stage="Zone Visit",
                count=zone_visitors,
                drop_off_pct=drop_off(
                    zone_visitors, total_entries
                )
            ),
            FunnelStage(
                stage="Billing Queue",
                count=billing_visitors,
                drop_off_pct=drop_off(
                    billing_visitors, zone_visitors
                )
            ),
            FunnelStage(
                stage="Purchase",
                count=purchases,
                drop_off_pct=drop_off(
                    purchases, billing_visitors
                )
            )
        ]

        logger.info(
            f"store_id={store_id} funnel="
            f"entry={total_entries} zone={zone_visitors} "
            f"billing={billing_visitors} purchase={purchases}"
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