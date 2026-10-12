from fastapi import FastAPI, HTTPException, status
from contextlib import asynccontextmanager
from database import init_database, get_db_session_factory, get_db_engine
from config import settings
import logging

# Configure logging with validation
def _get_log_level():
    """Get and validate log level, defaulting to INFO if invalid."""
    level_str = settings.log_level.upper()
    if not hasattr(logging, level_str):
        return logging.INFO
    return getattr(logging, level_str)

logging.basicConfig(
    level=_get_log_level(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import routers
from routers.whatsapp_webhook import router as whatsapp_router
from routers.telegram_webhook import router as telegram_router
from routers.aotg_telegram_webhook import router as aotg_telegram_router

# Global session factory (initialized in lifespan)
SessionLocal = None


def get_db():
    """Dependency to get database session."""
    if SessionLocal is None:
        raise RuntimeError("Database not initialized")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info("Starting Sales Admin Autocount AI Agent System")
    logger.info(f"Environment: {settings.environment}")

    # Log database type/host only (hide credentials)
    db_url = settings.database_url
    if db_url.startswith("sqlite"):
        logger.info("Database: SQLite")
    elif "://@" in db_url:
        # URL contains credentials
        protocol, rest = db_url.split("://", 1)
        if "/" in rest:
            host_part = rest.split("/")[0]
            logger.info(f"Database: {protocol}://{host_part}/...")
        else:
            logger.info(f"Database: {protocol}://...")
    else:
        logger.info("Database: configured")

    # Initialize database
    init_database(settings.database_url)
    global SessionLocal
    SessionLocal = get_db_session_factory()

    yield
    # Shutdown
    logger.info("Shutting down Sales Admin Autocount AI Agent System")


# Create FastAPI app
app = FastAPI(
    title="Sales Admin Autocount AI Agent System",
    description="AI Agent System for Office Admin & Sales Workflow — Wire Mesh Manufacturing",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware disabled - Telegram/WhatsApp webhooks do not require CORS
# If a browser frontend is added later, configure specific origins instead of wildcard


@app.get("/")
async def root():
    """Root endpoint for health check."""
    return {
        "status": "running",
        "version": "0.1.0"
    }


@app.get("/health")
async def health_check():
    """Liveness check - always returns 200 if service is running."""
    return {
        "status": "healthy"
    }


@app.get("/ready")
async def readiness_check():
    """Readiness check - verifies database connectivity."""
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return {
            "status": "ready",
            "database": "connected"
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready"
        )


# Include routers
app.include_router(whatsapp_router, prefix="/api/v1", tags=["webhook-whatsapp"])
app.include_router(telegram_router, prefix="/api/v1", tags=["webhook-telegram"])
app.include_router(aotg_telegram_router, prefix="/api/v1", tags=["webhook-aotg-telegram"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "development"
    )
