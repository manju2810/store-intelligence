from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from database import get_db, EventModel, POSTransaction
from models import EventBatch, IngestResponse
import logging
import uuid
from datetime import datetime
import pandas as pd
import os

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/ingest", response_model=IngestResponse)
async def ingest_events(batch: EventBatch, db: AsyncSession = Depends(get_db)):
    accepted = 0
    rejected = 0
    duplicate = 0
    errors = []

    for event in batch.events:
        try:
            # Check for duplicate
            existing = await db.execute(
                select(EventModel).where(EventModel.event_id == event.event_id)
            )
            if existing.scalar_one_or_none():
                duplicate += 1
                continue

            # Save event
            db_event = EventModel(
                event_id    = event.event_id,
                store_id    = event.store_id,
                camera_id   = event.camera_id,
                visitor_id  = event.visitor_id,
                event_type  = event.event_type,
                timestamp   = event.timestamp,
                zone_id     = event.zone_id,
                dwell_ms    = event.dwell_ms,
                is_staff    = event.is_staff,
                confidence  = event.confidence,
                queue_depth = event.metadata.queue_depth,
                sku_zone    = event.metadata.sku_zone,
                session_seq = event.metadata.session_seq,
                ingested_at = datetime.utcnow()
            )
            db.add(db_event)
            accepted += 1

        except Exception as e:
            rejected += 1
            errors.append(f"event_id={event.event_id} error={str(e)}")
            logger.error(f"Failed to ingest event {event.event_id}: {e}")

    # Load POS transactions on first ingest
    await load_pos_transactions(db)

    await db.commit()

    logger.info(
        f"Ingest complete: accepted={accepted} "
        f"rejected={rejected} duplicate={duplicate}"
    )

    return IngestResponse(
        accepted=accepted,
        rejected=rejected,
        duplicate=duplicate,
        errors=errors
    )

async def load_pos_transactions(db: AsyncSession):
    """Load POS transactions from CSV into database"""
    csv_path = os.getenv("POS_CSV", "/app/data/pos_transactions.csv")

    if not os.path.exists(csv_path):
        return

    try:
        # Check if already loaded
        result = await db.execute(
            text("SELECT COUNT(*) FROM pos_transactions")
        )
        count = result.scalar()
        if count and count > 0:
            return

        df = pd.read_csv(csv_path)

        for _, row in df.iterrows():
            # Parse timestamp
            timestamp = f"{row['order_date']} {row['order_time']}"
            try:
                dt = datetime.strptime(timestamp, "%d-%m-%Y %H:%M:%S")
                iso_timestamp = dt.isoformat() + "Z"
            except:
                iso_timestamp = timestamp

            # Check duplicate
            existing = await db.execute(
                select(POSTransaction).where(
                    POSTransaction.transaction_id == str(row['invoice_number'])
                )
            )
            if existing.scalar_one_or_none():
                continue

            pos = POSTransaction(
                transaction_id  = str(row['invoice_number']),
                store_id        = str(row['store_id']),
                order_id        = str(row['order_id']),
                timestamp       = iso_timestamp,
                basket_value    = float(row.get('total_amount', 0) or 0),
                customer_name   = str(row.get('customer_name', '')),
                customer_number = str(row.get('customer_number', ''))
            )
            db.add(pos)

        logger.info("POS transactions loaded successfully")

    except Exception as e:
        logger.error(f"Failed to load POS transactions: {e}")