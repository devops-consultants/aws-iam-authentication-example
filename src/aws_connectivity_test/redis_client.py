"""
Redis Client with AWS ElastiCache IAM Authentication
====================================================

This module provides a Redis client using redis-py that supports:
- Traditional password-based connections (for local development)
- AWS ElastiCache IAM authentication via presigned URLs (for production)

ElastiCache IAM Authentication Flow:
-----------------------------------
When `redis_use_iam_auth` is enabled:

1. The client uses a custom CredentialProvider
2. The provider generates a presigned URL using botocore RequestSigner
3. The presigned URL is used as the password for SASL authentication
4. Tokens are cached for 15 minutes to minimize API calls

The IAM authentication uses the same AWS credentials available to the pod
via IRSA (IAM Roles for Service Accounts).

Status Tracking:
---------------
This client provides methods for tracking message processing status:
- set_status: Update status at a pipeline stage
- get_status: Retrieve status for a specific message
- get_all_statuses: List recent message statuses

Each status entry is stored as a Redis hash with TTL to prevent unbounded growth.

Usage:
------
    from aws_connectivity_test.redis_client import RedisClient
    from aws_connectivity_test.config import get_settings

    async def main():
        settings = get_settings()
        client = RedisClient(settings)

        await client.connect()

        # Track status
        await client.set_status(
            message_id="msg-123",
            stage="kafka_consumed",
            details={"topic": "test", "offset": 42}
        )

        # Get status
        status = await client.get_status("msg-123")
        print(status)

        await client.close()
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Optional, Tuple, Union
from urllib.parse import ParseResult, urlencode, urlunparse

import redis
from redis.asyncio import Redis as AsyncRedis

from .config import Settings
from .exceptions import RedisConnectionError, RedisOperationError
from .logging_config import get_logger

# Get a logger for this module
logger = get_logger(__name__)


# =============================================================================
# ElastiCache IAM Credential Provider
# =============================================================================
# This provider generates IAM-signed tokens for ElastiCache authentication.
# Tokens are cached for 15 minutes (900 seconds) to reduce authentication overhead.
# =============================================================================


class ElastiCacheIAMProvider(redis.CredentialProvider):
    """
    Credential provider for AWS ElastiCache IAM authentication.

    This provider uses botocore to generate presigned URLs that serve as
    authentication tokens for ElastiCache. The tokens are signed using
    AWS SigV4 and are valid for 15 minutes.

    The presigned URL generation follows the AWS documentation for
    ElastiCache IAM authentication:
    https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/auth-iam.html

    Attributes:
        user: The Redis/ElastiCache username (usually 'default')
        cluster_name: The ElastiCache replication group ID
        region: AWS region where ElastiCache is deployed
        request_signer: botocore RequestSigner for generating presigned URLs
    """

    def __init__(
        self,
        user: str,
        cluster_name: str,
        region: str = "eu-west-2",
    ) -> None:
        """
        Initialize the ElastiCache IAM credential provider.

        Args:
            user: Redis username (usually 'default' for ElastiCache)
            cluster_name: ElastiCache replication group ID (cluster name)
            region: AWS region where ElastiCache is deployed
        """
        self.user = user
        self.cluster_name = cluster_name
        self.region = region

        # Import botocore for signing
        try:
            import botocore.session
            from botocore.model import ServiceId
            from botocore.signers import RequestSigner
        except ImportError as e:
            logger.error("botocore not installed", error=str(e))
            raise RedisConnectionError(
                "botocore is required for ElastiCache IAM authentication"
            )

        # Get AWS credentials from the environment (IRSA provides these)
        session = botocore.session.get_session()

        # Create the request signer for ElastiCache
        # This signer will use the IAM credentials from IRSA to sign requests
        self.request_signer = RequestSigner(
            ServiceId("elasticache"),  # Service name for signing
            self.region,
            "elasticache",  # Signing name
            "v4",  # Signature version (SigV4)
            session.get_credentials(),
            session.get_component("event_emitter"),
        )

        # Token cache: stores the last generated token with expiry time
        # This avoids regenerating tokens on every operation
        self._cached_token: Optional[str] = None
        self._token_expiry: float = 0

        logger.info(
            "ElastiCache IAM credential provider initialized",
            user=user,
            cluster_name=cluster_name,
            region=region,
        )

    def get_credentials(self) -> Union[Tuple[str], Tuple[str, str]]:
        """
        Get IAM credentials for ElastiCache authentication.

        This method generates a presigned URL that serves as the password
        for ElastiCache IAM authentication. The URL is cached for 15 minutes
        (with a small buffer) to minimize API calls.

        Returns:
            Tuple of (username, password/token) for authentication
        """
        # Check if we have a valid cached token
        current_time = time.time()
        if self._cached_token and current_time < self._token_expiry:
            logger.debug(
                "Using cached IAM token",
                expires_in_seconds=int(self._token_expiry - current_time),
            )
            return (self.user, self._cached_token)

        # Generate a new presigned URL token
        logger.debug("Generating new ElastiCache IAM token...")
        start_time = time.time()

        try:
            # Build the connect action URL
            # ElastiCache IAM auth requires a specific URL format:
            # https://<cluster-name>/?Action=connect&User=<username>
            query_params = {"Action": "connect", "User": self.user}
            url = urlunparse(
                ParseResult(
                    scheme="https",
                    netloc=self.cluster_name,
                    path="/",
                    query=urlencode(query_params),
                    params="",
                    fragment="",
                )
            )

            # Generate the presigned URL with SigV4 signature
            # The URL is valid for 900 seconds (15 minutes)
            signed_url = self.request_signer.generate_presigned_url(
                {"method": "GET", "url": url, "body": {}, "headers": {}, "context": {}},
                operation_name="connect",
                expires_in=900,  # 15 minutes
                region_name=self.region,
            )

            # ElastiCache requires the URL without the https:// prefix
            # The signed URL includes the signature in the query parameters
            token = signed_url.removeprefix("https://")

            # Cache the token with a small buffer before expiry
            # Use 14 minutes (840 seconds) to be safe
            self._cached_token = token
            self._token_expiry = current_time + 840

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "ElastiCache IAM token generated",
                token_length=len(token),
                duration_ms=duration_ms,
                expires_in_seconds=840,
            )

            return (self.user, token)

        except Exception as e:
            logger.error(
                "Failed to generate ElastiCache IAM token",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise RedisConnectionError(
                f"Failed to generate ElastiCache IAM token: {e}",
                details={"cluster_name": self.cluster_name, "region": self.region},
            )


# =============================================================================
# Redis Client
# =============================================================================


class RedisClient:
    """
    Redis client with optional ElastiCache IAM authentication.

    This client provides status tracking functionality for the message
    processing pipeline. It supports both local Redis (password auth)
    and AWS ElastiCache (IAM auth).

    Status Data Structure:
    Each message status is stored as a Redis hash with key 'status:{message_id}'.
    The hash contains:
    - message_id: UUID of the message
    - created_at: ISO timestamp when status was created
    - current_stage: Latest pipeline stage
    - stages: JSON dict of stage -> {timestamp, ...details}
    - error: Error message if pipeline failed (optional)

    Attributes:
        settings: Application settings containing Redis configuration
        client: Async Redis client instance (None until connect())
        _connected: Whether the client is connected
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the Redis client.

        Args:
            settings: Application settings with Redis configuration
        """
        self.settings = settings
        self.client: Optional[AsyncRedis] = None
        self._connected = False

        # Log initialization
        logger.info(
            "Redis client initialized",
            host=settings.redis_host,
            port=settings.redis_port,
            use_iam_auth=settings.redis_use_iam_auth,
            enabled=settings.redis_enabled,
            status_ttl=settings.redis_status_ttl,
        )

    async def connect(self) -> None:
        """
        Connect to Redis/ElastiCache.

        This method:
        1. Configures the client with appropriate authentication
        2. Creates the async Redis client
        3. Validates connectivity with a PING

        Raises:
            RedisConnectionError: If connection fails
        """
        if not self.settings.redis_enabled:
            logger.info("Redis is disabled, skipping connection")
            return

        start_time = time.time()
        logger.info(
            "Connecting to Redis...",
            host=self.settings.redis_host,
            port=self.settings.redis_port,
            use_iam_auth=self.settings.redis_use_iam_auth,
        )

        try:
            # Build connection parameters
            connection_kwargs: dict[str, Any] = {
                "host": self.settings.redis_host,
                "port": self.settings.redis_port,
                "decode_responses": True,  # Automatically decode bytes to strings
            }

            # Configure authentication
            if self.settings.redis_use_iam_auth:
                # Use ElastiCache IAM authentication
                logger.info("Configuring ElastiCache IAM authentication...")

                if not self.settings.redis_cluster_name:
                    raise RedisConnectionError(
                        "redis_cluster_name is required for IAM authentication",
                        details={"host": self.settings.redis_host},
                    )

                # Create the IAM credential provider
                creds_provider = ElastiCacheIAMProvider(
                    user=self.settings.redis_user,
                    cluster_name=self.settings.redis_cluster_name,
                    region=self.settings.aws_region,
                )
                connection_kwargs["credential_provider"] = creds_provider

                # ElastiCache requires SSL/TLS
                connection_kwargs["ssl"] = True
                connection_kwargs["ssl_cert_reqs"] = "required"

                logger.info("ElastiCache IAM authentication configured")
            else:
                logger.info("Using local Redis connection (no authentication)")

            # Create the async Redis client
            self.client = AsyncRedis(**connection_kwargs)

            # Validate connectivity
            logger.debug("Testing Redis connection with PING...")
            pong = await self.client.ping()

            if not pong:
                raise RedisConnectionError("Redis PING did not return PONG")

            self._connected = True
            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Redis connection successful",
                host=self.settings.redis_host,
                port=self.settings.redis_port,
                duration_ms=duration_ms,
            )

        except RedisConnectionError:
            raise
        except Exception as e:
            logger.error(
                "Redis connection failed",
                error=str(e),
                error_type=type(e).__name__,
                host=self.settings.redis_host,
                port=self.settings.redis_port,
            )
            raise RedisConnectionError(
                f"Failed to connect to Redis: {e}",
                details={
                    "host": self.settings.redis_host,
                    "port": self.settings.redis_port,
                },
            )

    async def close(self) -> None:
        """
        Close the Redis connection.

        This method should be called during graceful shutdown.
        """
        if self.client:
            logger.info("Closing Redis connection...")
            await self.client.close()
            self.client = None
            self._connected = False
            logger.info("Redis connection closed")

    # =========================================================================
    # Status Tracking Methods
    # =========================================================================

    async def set_status(
        self,
        message_id: str,
        stage: str,
        details: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Set the processing status for a message at a specific pipeline stage.

        This method updates the status hash in Redis with the current stage
        information. If this is the first status for the message, it creates
        the initial structure.

        Args:
            message_id: Unique identifier for the message (UUID)
            stage: Pipeline stage name (e.g., 'kafka_consumed', 'embedding_generated')
            details: Additional details about the stage (optional)
            error: Error message if the stage failed (optional)

        Raises:
            RedisOperationError: If the operation fails
        """
        if not self.settings.redis_enabled:
            logger.debug("Redis disabled, skipping status update")
            return

        if not self.client:
            logger.warning("Redis not connected, skipping status update")
            return

        start_time = time.time()
        key = f"status:{message_id}"
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            # Check if this is a new message or existing
            exists = await self.client.exists(key)

            if not exists:
                # Create new status entry
                initial_data = {
                    "message_id": message_id,
                    "created_at": timestamp,
                    "current_stage": stage,
                    "stages": json.dumps({}),
                }
                await self.client.hset(key, mapping=initial_data)

            # Update the stages dictionary
            stages_json = await self.client.hget(key, "stages")
            stages = json.loads(stages_json) if stages_json else {}

            # Add the new stage with timestamp and details
            stage_data = {"timestamp": timestamp}
            if details:
                stage_data.update(details)

            stages[stage] = stage_data

            # Build update data
            update_data: dict[str, str] = {
                "current_stage": stage,
                "stages": json.dumps(stages),
            }

            if error:
                update_data["error"] = error

            # Update the hash
            await self.client.hset(key, mapping=update_data)

            # Set/refresh TTL
            await self.client.expire(key, self.settings.redis_status_ttl)

            duration_ms = int((time.time() - start_time) * 1000)
            logger.debug(
                "Status updated",
                message_id=message_id,
                stage=stage,
                has_error=error is not None,
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.error(
                "Failed to set status",
                error=str(e),
                error_type=type(e).__name__,
                message_id=message_id,
                stage=stage,
            )
            raise RedisOperationError(
                f"Failed to set status for message {message_id}: {e}",
                details={"message_id": message_id, "stage": stage},
            )

    async def get_status(self, message_id: str) -> Optional[dict[str, Any]]:
        """
        Get the processing status for a specific message.

        Args:
            message_id: Unique identifier for the message

        Returns:
            Dictionary with status information, or None if not found

        Raises:
            RedisOperationError: If the operation fails
        """
        if not self.settings.redis_enabled:
            logger.debug("Redis disabled, returning None")
            return None

        if not self.client:
            logger.warning("Redis not connected, returning None")
            return None

        key = f"status:{message_id}"

        try:
            # Get all fields from the hash
            data = await self.client.hgetall(key)

            if not data:
                return None

            # Parse the stages JSON
            result = dict(data)
            if "stages" in result:
                result["stages"] = json.loads(result["stages"])

            return result

        except Exception as e:
            logger.error(
                "Failed to get status",
                error=str(e),
                error_type=type(e).__name__,
                message_id=message_id,
            )
            raise RedisOperationError(
                f"Failed to get status for message {message_id}: {e}",
                details={"message_id": message_id},
            )

    async def get_all_statuses(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Get all recent message statuses.

        This method scans for all status keys and returns their values.
        Results are ordered by creation time (most recent first).

        Args:
            limit: Maximum number of statuses to return (default 100)

        Returns:
            List of status dictionaries

        Raises:
            RedisOperationError: If the operation fails
        """
        if not self.settings.redis_enabled:
            logger.debug("Redis disabled, returning empty list")
            return []

        if not self.client:
            logger.warning("Redis not connected, returning empty list")
            return []

        try:
            # Scan for all status keys
            statuses: list[dict[str, Any]] = []
            cursor = 0

            while True:
                cursor, keys = await self.client.scan(
                    cursor=cursor,
                    match="status:*",
                    count=100,
                )

                for key in keys:
                    if len(statuses) >= limit:
                        break

                    data = await self.client.hgetall(key)
                    if data:
                        result = dict(data)
                        if "stages" in result:
                            result["stages"] = json.loads(result["stages"])
                        statuses.append(result)

                if cursor == 0 or len(statuses) >= limit:
                    break

            # Sort by created_at (most recent first)
            statuses.sort(
                key=lambda x: x.get("created_at", ""),
                reverse=True,
            )

            return statuses[:limit]

        except Exception as e:
            logger.error(
                "Failed to get all statuses",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise RedisOperationError(
                f"Failed to get all statuses: {e}",
            )

    # =========================================================================
    # Health Check
    # =========================================================================

    async def health_check(self) -> bool:
        """
        Check if Redis is healthy.

        Returns:
            True if Redis responds to PING, False otherwise
        """
        if not self.settings.redis_enabled:
            # If disabled, consider it "healthy" (not a failure)
            return True

        if not self.client:
            return False

        try:
            pong = await self.client.ping()
            return pong is True
        except Exception as e:
            logger.warning("Redis health check failed", error=str(e))
            return False

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected to Redis."""
        return self._connected and self.client is not None
