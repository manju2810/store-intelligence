from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from database import get_db
from models import HeatmapResponse, HeatmapZone
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/{store_id}/heatmap", response_model=HeatmapResponse)
async def get_heatmap(store_id: str, db: AsyncSession = Depends(get_db)):
    try:
        # ── Get zone visit frequency and dwell ───────────
        result = await db.execute(
            text("""
                SELECT
                    zone_id,
                    COUNT(DISTINCT visitor_id) as visit_count,
                    AVG(dwell_ms) as avg_dwell,
                    COUNT(DISTINCT visitor_id) as session_count
                FROM events
                WHERE store_id = :store_id
                AND is_staff = 0
                AND zone_id IS NOT NULL
                AND zone_id NOT IN ('ENTRY', 'EXIT')
                AND event_type IN ('ZONE_ENTER', 'ZONE_DWELL')
                GROUP BY zone_id
            """),
            {"store_id": store_id}
        )
        rows = result.fetchall()

        if not rows:
            return HeatmapResponse(
                store_id=store_id,
                zones=[]
            )

        # ── Normalize scores 0-100 ───────────────────────
        visit_counts = [row[1] for row in rows]
        max_visits = max(visit_counts) if visit_counts else 1
        min_visits = min(visit_counts) if visit_counts else 0

        def normalize(value, min_val, max_val):
            if max_val == min_val:
                return 50.0
            return round((value - min_val) / (max_val - min_val) * 100, 2)

        zones = []
        for row in rows:
            zone_id = row[0]
            visit_count = row[1]
            avg_dwell_ms = row[2] or 0
            session_count = row[3]

            # Low confidence if fewer than 20 sessions
            data_confidence = session_count >= 20

            zones.append(
                HeatmapZone(
                    zone_id=zone_id,
                    zone_name=zone_id.replace("_", " ").title(),
                    visit_frequency=visit_count,
                    avg_dwell_seconds=round(avg_dwell_ms / 1000, 2),
                    normalized_score=normalize(
                        visit_count, min_visits, max_visits
                    ),
                    data_confidence=data_confidence
                )
            )

        # Sort by normalized score descending
        zones.sort(key=lambda x: x.normalized_score, reverse=True)

        logger.info(
            f"store_id={store_id} "
            f"heatmap zones={len(zones)}"
        )

        return HeatmapResponse(
            store_id=store_id,
            zones=zones
        )

    except Exception as e:
        logger.error(f"Heatmap error for {store_id}: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Service unavailable",
                "detail": str(e)
            }
        )