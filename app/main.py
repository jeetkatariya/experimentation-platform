"""
Experimentation API - A/B Testing Platform

A FastAPI application for managing experiments, assigning users to variants,
recording events, and analyzing experiment results.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time

from app.config import settings
from app.database import init_db
from app.routers import experiments, assignments, events, results
from app.routers import auth_routes

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle management.
    Initializes database on startup.
    """
    logger.info("Starting Experimentation API...")
    init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down Experimentation API...")


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_timing(request: Request, call_next):
    """Add request timing header for performance monitoring."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


@app.get("/health", tags=["health"])
async def health_check():
    """
    Health check endpoint for load balancers and monitoring.
    Returns service status and version.
    """
    return {
        "status": "healthy",
        "version": settings.api_version,
        "service": "experimentation-api"
    }


@app.get("/", tags=["health"])
async def root():
    """Root endpoint with API information."""
    return {
        "service": settings.api_title,
        "version": settings.api_version,
        "docs": "/docs",
        "health": "/health",
        "auth": "/auth/token",
        "authentication": "JWT Bearer Token - Get token from POST /auth/token"
    }


app.include_router(auth_routes.router)  
app.include_router(experiments.router)
app.include_router(assignments.router)
app.include_router(events.router)
app.include_router(results.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unexpected errors.
    Logs the error and returns a sanitized response.
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again later."}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

