"""
Custom Exceptions for AWS Connectivity Test Service
====================================================

This module defines custom exception classes for the service. Using specific
exception types allows for:
- Clear error identification in logs
- Targeted error handling in different parts of the application
- Better debugging with context-rich error messages

Exception Hierarchy:
-------------------
ConnectivityTestError (base)
├── KafkaError
│   ├── KafkaConnectionError
│   └── KafkaConsumerError
├── PostgresError
│   ├── PostgresConnectionError
│   └── PostgresQueryError
├── OpenSearchError
│   ├── OpenSearchConnectionError
│   └── OpenSearchWriteError
└── OpenAIError
    ├── OpenAIConnectionError
    └── OpenAIEmbeddingError

Usage:
------
    from aws_connectivity_test.exceptions import KafkaConnectionError

    try:
        await connect_to_kafka()
    except KafkaConnectionError as e:
        logger.error("Kafka connection failed", error=str(e), details=e.details)
"""

from typing import Any, Optional


class ConnectivityTestError(Exception):
    """
    Base exception for all connectivity test errors.

    All custom exceptions in this service inherit from this class,
    allowing code to catch all service-specific errors with a single
    except clause if needed.

    Attributes:
        message: Human-readable error description
        details: Additional context about the error (optional)
    """

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        """
        Initialize the exception with a message and optional details.

        Args:
            message: Human-readable description of what went wrong
            details: Additional context (e.g., connection params, error codes)
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        """Return the error message, optionally with details."""
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


# =============================================================================
# Kafka / MSK Exceptions
# =============================================================================


class KafkaError(ConnectivityTestError):
    """Base exception for Kafka-related errors."""

    pass


class KafkaConnectionError(KafkaError):
    """
    Raised when connection to Kafka/MSK fails.

    This can happen due to:
    - Network connectivity issues
    - Invalid bootstrap servers
    - IAM authentication failures (for MSK)
    - SSL/TLS certificate issues
    """

    pass


class KafkaConsumerError(KafkaError):
    """
    Raised when Kafka consumer operations fail.

    This can happen due to:
    - Consumer group coordination failures
    - Partition assignment issues
    - Message deserialization errors
    - Offset commit failures
    """

    pass


# =============================================================================
# PostgreSQL / RDS Exceptions
# =============================================================================


class PostgresError(ConnectivityTestError):
    """Base exception for PostgreSQL-related errors."""

    pass


class PostgresConnectionError(PostgresError):
    """
    Raised when connection to PostgreSQL/RDS fails.

    This can happen due to:
    - Network connectivity issues
    - Invalid credentials or IAM token
    - Database does not exist
    - SSL/TLS issues
    - IAM authentication token expired or invalid
    """

    pass


class PostgresQueryError(PostgresError):
    """
    Raised when a PostgreSQL query fails.

    This can happen due to:
    - SQL syntax errors
    - Constraint violations
    - Permission denied
    - Table does not exist
    """

    pass


# =============================================================================
# OpenSearch Serverless Exceptions
# =============================================================================


class OpenSearchError(ConnectivityTestError):
    """Base exception for OpenSearch-related errors."""

    pass


class OpenSearchConnectionError(OpenSearchError):
    """
    Raised when connection to OpenSearch Serverless fails.

    This can happen due to:
    - Network connectivity issues
    - Invalid endpoint URL
    - IAM authentication failures (SigV4 signing)
    - Collection does not exist or is not active
    """

    pass


class OpenSearchWriteError(OpenSearchError):
    """
    Raised when writing to OpenSearch fails.

    This can happen due to:
    - Index does not exist
    - Document validation errors
    - Permission denied
    - Rate limiting
    """

    pass


# =============================================================================
# OpenAI Exceptions
# =============================================================================


class OpenAIError(ConnectivityTestError):
    """Base exception for OpenAI-related errors."""

    pass


class OpenAIConnectionError(OpenAIError):
    """
    Raised when connection to OpenAI API fails.

    This can happen due to:
    - Invalid API key
    - Network connectivity issues
    - API endpoint unreachable
    """

    pass


class OpenAIEmbeddingError(OpenAIError):
    """
    Raised when embedding generation fails.

    This can happen due to:
    - Rate limiting (429 errors)
    - Invalid model name
    - Input text too long
    - API timeout
    """

    pass


# =============================================================================
# Orchestrator Exceptions
# =============================================================================


class OrchestratorError(ConnectivityTestError):
    """Base exception for orchestrator-related errors."""

    pass


class StartupError(OrchestratorError):
    """
    Raised when service startup fails.

    This happens when any of the required AWS services cannot be
    connected during the startup sequence.
    """

    pass


class PipelineError(OrchestratorError):
    """
    Raised when the message processing pipeline fails.

    This includes errors in the consume → embed → store → log pipeline.
    The details dictionary includes information about which step failed.
    """

    pass


# =============================================================================
# Kafka Producer Exceptions
# =============================================================================


class KafkaProducerError(KafkaError):
    """
    Raised when Kafka producer operations fail.

    This can happen due to:
    - Message delivery failures
    - Producer flush timeouts
    - Serialization errors
    """

    pass


class KafkaPublishError(KafkaError):
    """
    Raised when publishing a message to Kafka fails.

    This can happen due to:
    - Topic does not exist
    - Message too large
    - Broker unavailable
    - Delivery confirmation timeout
    """

    pass


# =============================================================================
# Redis / ElastiCache Exceptions
# =============================================================================


class RedisError(ConnectivityTestError):
    """Base exception for Redis-related errors."""

    pass


class RedisConnectionError(RedisError):
    """
    Raised when connection to Redis/ElastiCache fails.

    This can happen due to:
    - Network connectivity issues
    - Invalid host or port
    - IAM authentication failures (for ElastiCache)
    - SSL/TLS certificate issues
    """

    pass


class RedisOperationError(RedisError):
    """
    Raised when a Redis operation fails.

    This can happen due to:
    - Key does not exist (for GET operations)
    - Memory limit exceeded
    - Command syntax errors
    - Connection timeout
    """

    pass
