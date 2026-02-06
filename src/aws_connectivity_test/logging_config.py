"""
Structured Logging Configuration for AWS Connectivity Test Service
===================================================================

This module configures structured logging using structlog, providing:
- JSON-formatted logs for production (CloudWatch, Grafana Loki)
- Human-readable console output for local development
- Consistent log structure across all service components

Log Structure:
-------------
Every log entry includes:
- timestamp: ISO 8601 format in UTC
- level: Log level (debug, info, warning, error)
- event: The log message
- service: Service name for filtering
- version: Service version for tracking

Additional context fields are added by each component:
- Kafka consumer: topic, partition, offset, consumer_group
- PostgreSQL client: operation, table, duration_ms
- OpenSearch client: index, doc_id, operation, duration_ms
- OpenAI client: model, input_length, dimensions, duration_ms

Usage:
------
    from aws_connectivity_test.logging_config import setup_logging, get_logger

    # Set up logging at application startup
    setup_logging(log_level="INFO", log_format="json")

    # Get a logger for your module
    logger = get_logger(__name__)

    # Log with structured context
    logger.info("Processing message", topic="my-topic", offset=12345)
"""

import logging
import sys
from typing import Any

import structlog


def setup_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    service_name: str = "aws-connectivity-test",
    service_version: str = "0.1.0",
) -> None:
    """
    Configure structured logging for the application.

    This function sets up both Python's standard logging and structlog.
    It should be called once at application startup before any logging occurs.

    Args:
        log_level: The minimum log level to output (DEBUG, INFO, WARNING, ERROR)
        log_format: Output format - 'json' for production, 'console' for development
        service_name: Service name to include in all log entries
        service_version: Service version to include in all log entries

    Example:
        # Production configuration
        setup_logging(log_level="INFO", log_format="json")

        # Development configuration
        setup_logging(log_level="DEBUG", log_format="console")
    """
    # -------------------------------------------------------------------------
    # Configure Python Standard Logging
    # -------------------------------------------------------------------------
    # We configure the root logger to output to stdout, which is the standard
    # for containerized applications. Kubernetes and CloudWatch capture stdout.
    # -------------------------------------------------------------------------
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # -------------------------------------------------------------------------
    # Build Structlog Processor Chain
    # -------------------------------------------------------------------------
    # Processors are functions that transform log entries as they flow through
    # the logging pipeline. Each processor adds or modifies log data.
    # -------------------------------------------------------------------------

    # Shared processors used for both console and JSON output
    shared_processors = [
        # Merge context variables from contextvars into the log entry
        # This allows setting context once (e.g., request_id) and having it
        # automatically included in all subsequent logs
        structlog.contextvars.merge_contextvars,
        # Add the log level (debug, info, warning, error) to the entry
        structlog.processors.add_log_level,
        # Add stack information for debugging when requested
        structlog.processors.StackInfoRenderer(),
        # Add exception information when logging errors
        structlog.dev.set_exc_info,
        # Add ISO 8601 timestamp in UTC for consistent time handling
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        # Add service identification to all log entries
        # This makes it easy to filter logs by service in CloudWatch/Grafana
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                structlog.processors.CallsiteParameter.MODULE,
            ]
        ),
    ]

    # -------------------------------------------------------------------------
    # Select Output Renderer Based on Format
    # -------------------------------------------------------------------------
    # JSON format is used in production for machine parsing
    # Console format is used in development for human readability
    # -------------------------------------------------------------------------
    if log_format.lower() == "json":
        # JSON renderer for production
        # Outputs one JSON object per line, which CloudWatch and Loki can parse
        processors = shared_processors + [
            # Add service metadata as top-level fields
            _add_service_info(service_name, service_version),
            # Render as JSON
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Console renderer for development
        # Outputs colored, human-readable logs with key=value formatting
        processors = shared_processors + [
            # Add service metadata as top-level fields
            _add_service_info(service_name, service_version),
            # Render as colored console output
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    # -------------------------------------------------------------------------
    # Configure Structlog
    # -------------------------------------------------------------------------
    structlog.configure(
        processors=processors,
        # Create a filtering logger that respects the log level
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        # Use dict for event context (standard, works everywhere)
        context_class=dict,
        # Use PrintLoggerFactory to output directly to stdout
        logger_factory=structlog.PrintLoggerFactory(),
        # Cache the logger configuration for performance
        cache_logger_on_first_use=True,
    )


def _add_service_info(
    service_name: str, service_version: str
) -> structlog.types.Processor:
    """
    Create a processor that adds service identification to log entries.

    This processor adds 'service' and 'version' fields to every log entry,
    making it easy to identify and filter logs from this service.

    Args:
        service_name: The name of the service
        service_version: The version of the service

    Returns:
        A structlog processor function
    """

    def processor(
        logger: Any, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        """Add service info to the event dictionary."""
        event_dict["service"] = service_name
        event_dict["version"] = service_version
        return event_dict

    return processor


def get_logger(name: str = __name__) -> Any:
    """
    Get a structured logger instance.

    This function returns a structlog logger that can be used to emit
    structured log entries. The logger supports method chaining and
    automatic context binding.

    Args:
        name: The name of the logger, typically __name__ for the calling module

    Returns:
        A structlog BoundLogger instance

    Example:
        logger = get_logger(__name__)

        # Simple logging
        logger.info("Service started")

        # Logging with context
        logger.info("Processing message", topic="my-topic", offset=12345)

        # Binding context for multiple logs
        log = logger.bind(request_id="abc-123")
        log.info("Step 1 complete")
        log.info("Step 2 complete")  # Also includes request_id
    """
    return structlog.get_logger(name)


def bind_context(**kwargs: Any) -> None:
    """
    Bind context variables that will be included in all subsequent logs.

    This is useful for setting context that should be included in all logs
    for a particular request or operation, such as a request ID or user ID.

    Args:
        **kwargs: Key-value pairs to bind to the logging context

    Example:
        # At the start of processing a Kafka message
        bind_context(
            kafka_topic="my-topic",
            kafka_partition=0,
            kafka_offset=12345,
        )

        # All subsequent logs in this context will include these fields
        logger.info("Processing message")  # Includes kafka_* fields
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """
    Clear all bound context variables.

    Call this when you want to reset the logging context, such as at the
    end of processing a message or request.

    Example:
        # After processing is complete
        clear_context()
    """
    structlog.contextvars.clear_contextvars()
