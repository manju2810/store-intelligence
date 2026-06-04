from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from database import get_db
from models import HealthResponse, StoreHealth
import logging
from datetime import datetime, timedelta

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/health", response_model=HealthResponse)
async def get_health(db: AsyncSession = Depends(get_db)):
    try:
        now = datetime.utcnow()

        # ── Get all stores ───────────────────────────────
        stores_result = await db.execute(
            text("""
                SELECT DISTINCT store_id
                FROM events
            """)
        )
        store_ids = [row[0] for row in stores_result.fetchall()]

        # ── If no stores yet return healthy ─────────────
        if not store_ids:
            return HealthResponse(
                status="OK",
                stores=[],
                timestamp=now.isoformat() + "Z"
            )

        stores = []
        overall_status = "OK"

        for store_id in store_ids:
            # Get last event timestamp
            last_event_result = await db.execute(
                text("""
                    SELECT MAX(timestamp)
                    FROM events
                    WHERE store_id = :store_id
                """),
                {"store_id": store_id}
            )
            last_event_ts = last_event_result.scalar()

            # Check if feed is stale (> 10 min ago)
            feed_status = "OK"
            if last_event_ts:
                try:
                    last_event_dt = datetime.fromisoformat(
                        last_event_ts.replace("Z", "")
                    )
                    diff_minutes = (
                        now - last_event_dt
                    ).total_seconds() / 60

                    if diff_minutes > 10:
                        feed_status = "STALE_FEED"
                        overall_status = "DEGRADED"
                except Exception:
                    feed_status = "UNKNOWN"
            else:
                feed_status = "NO_FEED"
                overall_status = "DEGRADED"

            stores.append(
                StoreHealth(
                    store_id=store_id,
                    status="OK" if feed_status == "OK" else "DEGRADED",
                    last_event_timestamp=last_event_ts,
                    feed_status=feed_status
                )
            )

        logger.info(
            f"Health check: status={overall_status} "
            f"stores={len(stores)}"
        )

        return HealthResponse(
            status=overall_status,
            stores=stores,
            timestamp=now.isoformat() + "Z"
        )

    except Exception as e:
        logger.error(f"Health check error: {e}")
        return HealthResponse(
            status="ERROR",
            stores=[],
            timestamp=datetime.utcnow().isoformat() + "Z"
        )