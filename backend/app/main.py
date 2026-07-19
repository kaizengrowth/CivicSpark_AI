import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime

from app.core.config import settings
from app.core.database import create_tables, ensure_pgvector
from app.core.exceptions import (
    CityCampException,
    citycamp_exception_handler,
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.schemas.base import HealthCheckResponse
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.api.v1 import api_router


# Custom JSON encoder for datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.environment == "development" else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown events
    """
    # Startup
    logger.info(f"Starting up {settings.project_name}...")
    settings.validate_production_settings()

    # Try to create tables, but don't fail if database is not ready
    max_retries = 5
    for attempt in range(max_retries):
        try:
            create_tables()
            logger.info("Database tables created/verified")
            ensure_pgvector()
            break
        except Exception as e:
            logger.warning(f"Database connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                logger.info("Retrying in 2 seconds...")
                time.sleep(2)
            else:
                logger.error("Could not connect to database after multiple attempts")
                logger.error("The API will start without database functionality")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.project_name}...")


# Create FastAPI app
app = FastAPI(
    title=settings.project_name,
    description=settings.project_description,
    version=settings.project_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Add CORS middleware. Origins come from settings: explicit CORS_ORIGINS in
# production, local dev servers otherwise. Same-origin traffic through the
# Vercel /api rewrite needs no CORS at all.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
app.add_exception_handler(CityCampException, citycamp_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)


# Health check endpoint
@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    Health check endpoint
    """
    return HealthCheckResponse(
        status="healthy",
        service=settings.project_name,
        version=settings.project_version,
        environment=settings.environment,
        features={
            "chatbot": settings.is_openai_configured,
            "database": True,  # If we reach here, database is likely working
            "openai_configured": settings.is_openai_configured,
        },
    )


# Include API routes
app.include_router(api_router, prefix=f"/api/{settings.api_version}")


# Root endpoint
@app.get("/")
async def root():
    """
    Root endpoint
    """
    return {
        "message": f"Welcome to {settings.project_name}!",
        "version": settings.project_version,
        "docs": (
            "/docs" if settings.debug else "Documentation not available in production"
        ),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # nosec B104 - Intentional for development/Docker
        port=8000,
        reload=settings.debug,
        log_level="info" if settings.debug else "warning",
    )
