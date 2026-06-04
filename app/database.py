from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, String, Float, Boolean, Integer, DateTime, Text
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/store.db")

# Fix for async sqlite
if DATABASE_URL.startswith("sqlite:///"):
    DATABASE_URL = DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///")

engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

# ── Tables ──────────────────────────────────────────────

class EventModel(Base):
    __tablename__ = "events"

    event_id       = Column(String, primary_key=True)
    store_id       = Column(String, nullable=False, index=True)
    camera_id      = Column(String, nullable=False)
    visitor_id     = Column(String, nullable=False, index=True)
    event_type     = Column(String, nullable=False)
    timestamp      = Column(String, nullable=False)
    zone_id        = Column(String, nullable=True)
    dwell_ms       = Column(Integer, default=0)
    is_staff       = Column(Boolean, default=False)
    confidence     = Column(Float, default=1.0)
    queue_depth    = Column(Integer, nullable=True)
    sku_zone       = Column(String, nullable=True)
    session_seq    = Column(Integer, default=0)
    ingested_at    = Column(DateTime, default=datetime.utcnow)

class POSTransaction(Base):
    __tablename__ = "pos_transactions"

    transaction_id  = Column(String, primary_key=True)
    store_id        = Column(String, nullable=False, index=True)
    order_id        = Column(String, nullable=False)
    timestamp       = Column(String, nullable=False)
    basket_value    = Column(Float, default=0.0)
    customer_name   = Column(String, nullable=True)
    customer_number = Column(String, nullable=True)

class AnomalyModel(Base):
    __tablename__ = "anomalies"

    id              = Column(String, primary_key=True)
    store_id        = Column(String, nullable=False, index=True)
    anomaly_type    = Column(String, nullable=False)
    severity        = Column(String, nullable=False)
    description     = Column(Text, nullable=False)
    suggested_action= Column(Text, nullable=False)
    detected_at     = Column(DateTime, default=datetime.utcnow)
    resolved        = Column(Boolean, default=False)

# ── Helpers ─────────────────────────────────────────────

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()