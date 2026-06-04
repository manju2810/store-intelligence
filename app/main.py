from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time
import uuid
import logging
from database import init_db
from routers import events, metrics, funnel, heatmap, anomalies, health

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Store Intelligence API")
    await init_db()
    logger.info("Database initialised")
    yield
    # Shutdown
    logger.info("Shutting down Store Intelligence API")

app = FastAPI(
    title="Store Intelligence API",
    description="Real-time retail store analytics from CCTV footage",
    version="1.0.0",
    lifespan=lifespan
)

# Middleware for structured logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    trace_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    
    try:
        response = await call_next(request)
        latency_ms = round((time.time() - start_time) * 1000, 2)
        
        logger.info(
            f"trace_id={trace_id} "
            f"endpoint={request.url.path} "
            f"method={request.method} "
            f"status_code={response.status_code} "
            f"latency_ms={latency_ms}"
        )
        return response
    except Exception as e:
        latency_ms = round((time.time() - start_time) * 1000, 2)
        logger.error(
            f"trace_id={trace_id} "
            f"endpoint={request.url.path} "
            f"error={str(e)} "
            f"latency_ms={latency_ms}"
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "trace_id": trace_id}
        )

# Include routers
app.include_router(events.router, prefix="/events", tags=["Events"])
app.include_router(metrics.router, prefix="/stores", tags=["Metrics"])
app.include_router(funnel.router, prefix="/stores", tags=["Funnel"])
app.include_router(heatmap.router, prefix="/stores", tags=["Heatmap"])
app.include_router(anomalies.router, prefix="/stores", tags=["Anomalies"])
app.include_router(health.router, tags=["Health"])

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=503,
        content={
            "error": "Service temporarily unavailable",
            "detail": str(exc)
        }
    )