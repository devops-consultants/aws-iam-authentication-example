"""
FastAPI Application for AWS Connectivity Test Service
=====================================================

This module defines the FastAPI application that serves as the entry point
for the AWS connectivity test service. It provides:
- Health check endpoints for Kubernetes probes
- Application lifecycle management (startup/shutdown)
- Integration with the orchestrator for message processing

Application Lifecycle:
---------------------
The application uses FastAPI's lifespan context manager to coordinate
startup and shutdown:

1. On startup:
   - Configure logging
   - Initialize the orchestrator
   - Connect to all AWS services
   - Start the Kafka consumer in a background task

2. On shutdown:
   - Stop the Kafka consumer
   - Close all service connections
   - Clean up resources

Health Endpoints:
----------------
- /health: Combined liveness and readiness check
  - Returns 200 OK when all services are healthy
  - Returns 503 Service Unavailable when any service is unhealthy
  - Used by Kubernetes for both liveness and readiness probes

Kubernetes Integration:
----------------------
This application is designed to run in Kubernetes with:
- Liveness probe: /health (detect crashes)
- Readiness probe: /health (detect not-ready state)
- SIGTERM handling: Graceful shutdown within configured timeout

Usage:
------
The application is started via uvicorn:

    uvicorn aws_connectivity_test.main:app --host 0.0.0.0 --port 8080

Or via Docker:

    docker run -p 8080:8080 aws-connectivity-test:latest
"""

import asyncio
import signal
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import __service_name__, __version__
from .config import get_settings
from .logging_config import get_logger, setup_logging
from .orchestrator import Orchestrator

# Get settings and configure logging early
settings = get_settings()
setup_logging(
    log_level=settings.log_level,
    log_format=settings.log_format,
    service_name=settings.service_name,
    service_version=settings.service_version,
)

# Get a logger for this module
logger = get_logger(__name__)

# Global orchestrator instance
# Initialized in the lifespan context manager
orchestrator: Orchestrator | None = None

# Background task for the consumer loop
consumer_task: asyncio.Task | None = None


# =============================================================================
# Application Lifespan Management
# =============================================================================
# The lifespan context manager handles application startup and shutdown.
# This is the recommended way to manage resources in FastAPI.
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage the application lifecycle.

    This context manager:
    - On enter: Initializes services and starts the consumer
    - On exit: Stops the consumer and closes all connections

    The orchestrator runs in a background task so the FastAPI event loop
    can continue handling HTTP requests (health checks).
    """
    global orchestrator, consumer_task

    logger.info(
        "Application lifespan starting",
        service=__service_name__,
        version=__version__,
    )

    # -------------------------------------------------------------------------
    # Startup
    # -------------------------------------------------------------------------
    try:
        # Create the orchestrator
        orchestrator = Orchestrator(settings)

        # Connect to all services
        await orchestrator.startup()

        # Start the consumer in a background task
        # This allows the FastAPI event loop to continue serving requests
        consumer_task = asyncio.create_task(
            orchestrator.run(),
            name="kafka-consumer",
        )

        logger.info("Application startup complete - ready for health checks")

        # Yield control to the application
        yield

    except Exception as e:
        logger.error(
            "Application startup failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise

    finally:
        # -------------------------------------------------------------------------
        # Shutdown
        # -------------------------------------------------------------------------
        logger.info("Application shutdown starting")

        # Cancel the consumer task
        if consumer_task and not consumer_task.done():
            logger.info("Cancelling consumer task...")
            consumer_task.cancel()
            try:
                await asyncio.wait_for(consumer_task, timeout=settings.shutdown_timeout)
            except asyncio.TimeoutError:
                logger.warning("Consumer task cancellation timed out")
            except asyncio.CancelledError:
                logger.debug("Consumer task cancelled successfully")

        # Shutdown the orchestrator
        if orchestrator:
            await orchestrator.shutdown()

        logger.info("Application shutdown complete")


# =============================================================================
# FastAPI Application
# =============================================================================
# Create the FastAPI app with lifespan management and metadata
# =============================================================================

app = FastAPI(
    title="AWS Connectivity Test Service",
    description=(
        "Test service for validating AWS connectivity (MSK, RDS, OpenSearch) "
        "with IAM authentication in Kubernetes environments."
    ),
    version=__version__,
    lifespan=lifespan,
)


# =============================================================================
# Health Check Endpoint
# =============================================================================
# This endpoint is used by Kubernetes for both liveness and readiness probes.
# It checks the health of all connected services.
# =============================================================================


@app.get(
    "/health",
    summary="Health check endpoint",
    description="Returns the health status of all connected services",
    responses={
        200: {"description": "All services healthy"},
        503: {"description": "One or more services unhealthy"},
    },
)
async def health_check() -> Response:
    """
    Check the health of all services.

    This endpoint is called by Kubernetes for:
    - Liveness probe: Detect if the application has crashed
    - Readiness probe: Detect if the application is ready for traffic

    Returns:
        200 OK with health details if all services are healthy
        503 Service Unavailable if any service is unhealthy
    """
    logger.debug("Health check requested")

    # If orchestrator isn't initialized, we're not healthy
    if not orchestrator:
        logger.warning("Health check failed - orchestrator not initialized")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "message": "Service not initialized",
            },
        )

    # Perform health check on all services
    health_status = await orchestrator.health_check()

    # Determine HTTP status code
    if health_status["healthy"]:
        logger.debug(
            "Health check passed",
            services=health_status["services"],
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy",
                "service": settings.service_name,
                "version": settings.service_version,
                "services": health_status["services"],
            },
        )
    else:
        logger.warning(
            "Health check failed",
            services=health_status["services"],
        )
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": settings.service_name,
                "version": settings.service_version,
                "services": health_status["services"],
            },
        )


@app.get(
    "/",
    summary="Root endpoint",
    description="Returns basic service information",
)
async def root() -> dict[str, Any]:
    """
    Return basic service information.

    This endpoint provides a simple way to verify the service is running
    and get basic information about it.
    """
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "running",
        "description": "AWS Connectivity Test Service",
    }


# =============================================================================
# Pydantic Models for API Endpoints
# =============================================================================


class PublishRequest(BaseModel):
    """Request body for publishing a message to Kafka."""

    content: str = Field(
        ...,
        description="Message content to publish",
        min_length=1,
        max_length=10000,
    )
    key: str | None = Field(
        default=None,
        description="Optional message key for partitioning",
    )


class PublishResponse(BaseModel):
    """Response from publishing a message."""

    message_id: str = Field(..., description="UUID for tracking the message")
    topic: str = Field(..., description="Kafka topic the message was published to")
    status: str = Field(default="published", description="Current status")


# =============================================================================
# Publish and Status Endpoints
# =============================================================================


@app.post(
    "/publish",
    summary="Publish a test message to Kafka",
    description="Publishes a message to Kafka for end-to-end testing",
    response_model=PublishResponse,
    responses={
        200: {"description": "Message published successfully"},
        500: {"description": "Failed to publish message"},
        503: {"description": "Service not initialized"},
    },
)
async def publish_message(request: PublishRequest) -> Response:
    """
    Publish a test message to Kafka.

    This endpoint allows publishing messages for end-to-end testing
    of the full pipeline: publish → consume → embed → store → log.

    The returned message_id can be used with the /status endpoint
    to track processing progress.
    """
    logger.info(
        "Publish request received",
        content_length=len(request.content),
        has_key=request.key is not None,
    )

    if not orchestrator:
        logger.warning("Publish failed - orchestrator not initialized")
        return JSONResponse(
            status_code=503,
            content={
                "error": "Service not initialized",
                "message": "The service is still starting up",
            },
        )

    try:
        message_id = await orchestrator.publish_message(
            content=request.content,
            key=request.key,
        )

        # Get the topic from settings
        topic = settings.kafka_topics.split(",")[0].strip()

        logger.info(
            "Message published successfully",
            message_id=message_id,
            topic=topic,
        )

        return JSONResponse(
            status_code=200,
            content={
                "message_id": message_id,
                "topic": topic,
                "status": "published",
            },
        )

    except Exception as e:
        logger.error(
            "Failed to publish message",
            error=str(e),
            error_type=type(e).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "Failed to publish message",
                "message": str(e),
            },
        )


@app.get(
    "/status",
    summary="Get processing status",
    description="Get the processing status for a specific message or list recent statuses",
    responses={
        200: {"description": "Status retrieved successfully"},
        503: {"description": "Service not initialized"},
    },
)
async def get_status(
    message_id: str | None = Query(
        default=None,
        description="Message ID to get status for (returns single status)",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of statuses to return (if no message_id)",
    ),
) -> Response:
    """
    Get processing status from Redis.

    If message_id is provided, returns the status for that specific message.
    Otherwise, returns a list of recent message statuses.

    Status includes:
    - message_id: Unique identifier
    - created_at: When the message was first tracked
    - current_stage: Latest pipeline stage
    - stages: Dictionary of all stages with timestamps
    - error: Error message if processing failed
    """
    logger.debug(
        "Status request received",
        message_id=message_id,
        limit=limit,
    )

    if not orchestrator:
        logger.warning("Status check failed - orchestrator not initialized")
        return JSONResponse(
            status_code=503,
            content={
                "error": "Service not initialized",
                "message": "The service is still starting up",
            },
        )

    try:
        result = await orchestrator.get_processing_status(
            message_id=message_id,
            limit=limit,
        )

        return JSONResponse(
            status_code=200,
            content=result,
        )

    except Exception as e:
        logger.error(
            "Failed to get status",
            error=str(e),
            error_type=type(e).__name__,
            message_id=message_id,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "Failed to get status",
                "message": str(e),
            },
        )


# =============================================================================
# Signal Handlers
# =============================================================================
# These handlers ensure graceful shutdown when the container receives signals.
# Kubernetes sends SIGTERM to stop pods gracefully.
# =============================================================================


def setup_signal_handlers() -> None:
    """
    Set up signal handlers for graceful shutdown.

    This function is called at module load time to register handlers
    for SIGTERM and SIGINT signals.
    """
    loop = asyncio.get_event_loop()

    def handle_signal(sig: signal.Signals) -> None:
        """Handle shutdown signals."""
        logger.info(
            "Received shutdown signal",
            signal=sig.name,
        )
        # The lifespan context manager will handle cleanup

    # Register signal handlers
    # These may fail in some environments (e.g., Windows)
    try:
        loop.add_signal_handler(signal.SIGTERM, lambda: handle_signal(signal.SIGTERM))
        loop.add_signal_handler(signal.SIGINT, lambda: handle_signal(signal.SIGINT))
        logger.debug("Signal handlers registered")
    except NotImplementedError:
        logger.debug("Signal handlers not supported on this platform")


# =============================================================================
# Module Initialization
# =============================================================================
# Log application information when the module is loaded
# =============================================================================

logger.info(
    "AWS Connectivity Test Service module loaded",
    service=__service_name__,
    version=__version__,
    log_level=settings.log_level,
)
