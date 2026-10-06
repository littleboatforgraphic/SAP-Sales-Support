from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from database import init_database, get_db_session_factory
from config import settings
import logging

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize database
init_database(settings.database_url)
SessionLocal = get_db_session_factory()


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info("Starting Sales Admin SAP AI Agent System")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Database: {settings.database_url}")
    yield
    # Shutdown
    logger.info("Shutting down Sales Admin SAP AI Agent System")


# Create FastAPI app
app = FastAPI(
    title="Sales Admin SAP AI Agent System",
    description="AI Agent System for Office Admin & Sales Workflow — Wire Mesh Manufacturing",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware (if needed for future web interface)
# Note: allow_credentials=True cannot be used with allow_origins=["*"]
# For now, disable credentials until specific origins are configured
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=False,  # Disabled due to wildcard origins
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint for health check."""
    return {
        "status": "running",
        "version": "0.1.0",
        "environment": settings.environment
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "database": "connected"  # TODO: Add actual DB health check
    }


# Import and include routers
from routers.whatsapp_webhook import router as whatsapp_router
from routers.telegram_webhook import router as telegram_router
app.include_router(whatsapp_router, prefix="/api/v1", tags=["webhook-whatsapp"])
app.include_router(telegram_router, prefix="/api/v1", tags=["webhook-telegram"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "development"
    )
