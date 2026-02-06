"""
PostgreSQL Client with IAM Authentication for AWS RDS
======================================================

This module provides an async PostgreSQL client that supports both:
- Traditional password-based authentication (for local development)
- AWS IAM authentication (for production with RDS)

IAM Authentication Flow:
-----------------------
When `postgresql_use_iam_auth` is enabled:

1. The client uses boto3 to generate an IAM authentication token
2. This token is a temporary password valid for 15 minutes
3. The token is used in place of the regular password
4. boto3 automatically uses credentials from IRSA in Kubernetes

The IAM token is generated using:
    boto3.client('rds').generate_db_auth_token(
        DBHostname=host,
        Port=port,
        DBUsername=user,
        Region=region
    )

Connection Pool:
---------------
The client uses asyncpg's connection pool for efficient connection management:
- Minimum connections are kept open for fast response times
- Maximum connections limit resource usage
- Connections are automatically recycled when tokens expire

Demo Log Table:
--------------
The client creates and manages a `demo_log` table that records all
message processing operations for verification purposes.

Usage:
------
    from aws_connectivity_test.postgres_client import PostgresClient
    from aws_connectivity_test.config import get_settings

    async def main():
        settings = get_settings()
        client = PostgresClient(settings)

        await client.connect()
        await client.insert_log_entry(
            kafka_topic="my-topic",
            kafka_partition=0,
            kafka_offset=12345,
            message_content="Hello, World!",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            opensearch_index="my-index",
            opensearch_doc_id="doc-123",
        )
        await client.close()
"""

import time
from typing import Any, Optional

import asyncpg
import boto3

from .config import Settings
from .exceptions import PostgresConnectionError, PostgresQueryError
from .logging_config import get_logger

# Get a logger for this module
logger = get_logger(__name__)


# =============================================================================
# SQL Statements
# =============================================================================
# Define SQL as constants for clarity and maintainability
# The demo_log table stores all message processing operations
# =============================================================================

CREATE_DEMO_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS demo_log (
    -- Primary key: auto-incrementing ID
    id SERIAL PRIMARY KEY,

    -- Timestamp when the log entry was created (defaults to now)
    timestamp TIMESTAMPTZ DEFAULT NOW(),

    -- Kafka message metadata
    kafka_topic TEXT NOT NULL,
    kafka_partition INTEGER NOT NULL,
    kafka_offset BIGINT NOT NULL,

    -- Message content (the actual Kafka message value)
    message_content TEXT,

    -- OpenAI embedding metadata
    embedding_model TEXT,
    embedding_dimensions INTEGER,

    -- OpenSearch storage metadata
    opensearch_index TEXT,
    opensearch_doc_id TEXT,

    -- Log level for filtering (INFO for success, ERROR for failures)
    log_level TEXT DEFAULT 'INFO',

    -- Error details if processing failed
    error_message TEXT,

    -- Processing metrics
    processing_duration_ms INTEGER
);

-- Create an index on timestamp for efficient time-range queries
CREATE INDEX IF NOT EXISTS idx_demo_log_timestamp ON demo_log (timestamp DESC);

-- Create an index on kafka_topic for filtering by topic
CREATE INDEX IF NOT EXISTS idx_demo_log_topic ON demo_log (kafka_topic);
"""

INSERT_LOG_ENTRY = """
INSERT INTO demo_log (
    kafka_topic,
    kafka_partition,
    kafka_offset,
    message_content,
    embedding_model,
    embedding_dimensions,
    opensearch_index,
    opensearch_doc_id,
    log_level,
    error_message,
    processing_duration_ms
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
RETURNING id, timestamp;
"""

CHECK_TABLE_EXISTS = """
SELECT EXISTS (
    SELECT FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name = 'demo_log'
);
"""


class PostgresClient:
    """
    Async PostgreSQL client with optional IAM authentication.

    This client manages connections to PostgreSQL/RDS, handles IAM token
    generation for authentication, and provides methods for the demo_log table.

    Attributes:
        settings: Application settings containing database configuration
        pool: asyncpg connection pool (None until connect() is called)
        _connected: Whether the client is connected
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the PostgreSQL client.

        Args:
            settings: Application settings with database configuration
        """
        self.settings = settings
        self.pool: Optional[asyncpg.Pool] = None
        self._connected = False

        # Log initialization
        logger.info(
            "PostgreSQL client initialized",
            host=settings.postgres_host,
            port=settings.postgres_port,
            database=settings.postgres_db,
            user=settings.postgres_user,
            use_iam_auth=settings.postgresql_use_iam_auth,
        )

    async def connect(self) -> None:
        """
        Connect to PostgreSQL and create the demo_log table.

        This method:
        1. Generates an IAM token if IAM auth is enabled
        2. Creates a connection pool
        3. Creates the demo_log table if it doesn't exist

        Raises:
            PostgresConnectionError: If connection fails
        """
        start_time = time.time()
        logger.info("Connecting to PostgreSQL...")

        try:
            # ---------------------------------------------------------------
            # Step 1: Determine the password to use
            # ---------------------------------------------------------------
            # For IAM auth, we generate a token using boto3
            # For password auth, we use the configured password
            # ---------------------------------------------------------------
            if self.settings.postgresql_use_iam_auth:
                logger.info("Generating IAM authentication token...")
                password = self._generate_iam_token()
                logger.info(
                    "IAM token generated successfully",
                    token_length=len(password),
                )
            else:
                logger.info("Using password authentication")
                password = self.settings.postgres_password

            # ---------------------------------------------------------------
            # Step 2: Create the connection pool
            # ---------------------------------------------------------------
            # asyncpg manages a pool of connections for efficiency
            # We use SSL for IAM auth (required by RDS)
            # ---------------------------------------------------------------
            logger.info(
                "Creating connection pool",
                min_size=self.settings.postgres_pool_min_size,
                max_size=self.settings.postgres_pool_max_size,
            )

            # Build connection kwargs
            connect_kwargs: dict[str, Any] = {
                "host": self.settings.postgres_host,
                "port": self.settings.postgres_port,
                "database": self.settings.postgres_db,
                "user": self.settings.postgres_user,
                "password": password,
                "min_size": self.settings.postgres_pool_min_size,
                "max_size": self.settings.postgres_pool_max_size,
            }

            # Enable SSL for IAM auth (RDS requires SSL for IAM connections)
            # or when explicitly configured via postgres_ssl setting
            if self.settings.postgresql_use_iam_auth:
                connect_kwargs["ssl"] = "require"
            elif self.settings.postgres_ssl and self.settings.postgres_ssl != "disable":
                connect_kwargs["ssl"] = self.settings.postgres_ssl

            self.pool = await asyncpg.create_pool(**connect_kwargs)
            self._connected = True

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "PostgreSQL connection pool created",
                duration_ms=duration_ms,
            )

            # ---------------------------------------------------------------
            # Step 3: Create the demo_log table
            # ---------------------------------------------------------------
            await self._ensure_demo_log_table()

            logger.info(
                "PostgreSQL client connected successfully",
                host=self.settings.postgres_host,
                database=self.settings.postgres_db,
                total_duration_ms=int((time.time() - start_time) * 1000),
            )

        except asyncpg.PostgresError as e:
            logger.error(
                "PostgreSQL connection failed",
                error=str(e),
                error_type=type(e).__name__,
                host=self.settings.postgres_host,
            )
            raise PostgresConnectionError(
                f"Failed to connect to PostgreSQL: {e}",
                details={
                    "host": self.settings.postgres_host,
                    "port": self.settings.postgres_port,
                    "database": self.settings.postgres_db,
                    "use_iam_auth": self.settings.postgresql_use_iam_auth,
                },
            )
        except Exception as e:
            logger.error(
                "Unexpected error connecting to PostgreSQL",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise PostgresConnectionError(f"Unexpected connection error: {e}")

    def _generate_iam_token(self) -> str:
        """
        Generate an IAM authentication token for RDS.

        This method uses boto3 to generate a temporary authentication token
        that can be used as a password for RDS connections. The token is
        valid for 15 minutes.

        In Kubernetes with IRSA:
        - boto3 automatically uses the service account's IAM role
        - No explicit credentials need to be configured
        - The role must have rds-db:connect permission

        Returns:
            The IAM authentication token (a temporary password)

        Raises:
            PostgresConnectionError: If token generation fails
        """
        logger.debug(
            "Generating IAM authentication token",
            region=self.settings.aws_region,
            host=self.settings.postgres_host,
            port=self.settings.postgres_port,
            user=self.settings.postgres_user,
        )

        try:
            # Create an RDS client
            # In Kubernetes with IRSA, boto3 automatically gets credentials
            # from the service account's IAM role via the IRSA webhook
            rds_client = boto3.client("rds", region_name=self.settings.aws_region)

            # Generate the authentication token
            # This token can be used as a password for 15 minutes
            token = rds_client.generate_db_auth_token(
                DBHostname=self.settings.postgres_host,
                Port=self.settings.postgres_port,
                DBUsername=self.settings.postgres_user,
                Region=self.settings.aws_region,
            )

            logger.debug("IAM token generated", token_length=len(token))
            return token

        except Exception as e:
            logger.error(
                "Failed to generate IAM token",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise PostgresConnectionError(
                f"Failed to generate IAM authentication token: {e}",
                details={"region": self.settings.aws_region},
            )

    async def _ensure_demo_log_table(self) -> None:
        """
        Create the demo_log table if it doesn't exist.

        This method is idempotent - it can be called multiple times safely.
        The table is created with indexes for efficient querying.
        """
        if not self.pool:
            raise PostgresConnectionError("Not connected to PostgreSQL")

        logger.info("Checking demo_log table...")

        try:
            async with self.pool.acquire() as conn:
                # Check if table exists
                exists = await conn.fetchval(CHECK_TABLE_EXISTS)

                if exists:
                    logger.info("demo_log table already exists")
                else:
                    logger.info("Creating demo_log table...")
                    await conn.execute(CREATE_DEMO_LOG_TABLE)
                    logger.info("demo_log table created successfully")

        except asyncpg.PostgresError as e:
            logger.error("Failed to create demo_log table", error=str(e))
            raise PostgresQueryError(
                f"Failed to create demo_log table: {e}",
                details={"table": "demo_log"},
            )

    async def insert_log_entry(
        self,
        kafka_topic: str,
        kafka_partition: int,
        kafka_offset: int,
        message_content: Optional[str] = None,
        embedding_model: Optional[str] = None,
        embedding_dimensions: Optional[int] = None,
        opensearch_index: Optional[str] = None,
        opensearch_doc_id: Optional[str] = None,
        log_level: str = "INFO",
        error_message: Optional[str] = None,
        processing_duration_ms: Optional[int] = None,
    ) -> tuple[int, Any]:
        """
        Insert a log entry into the demo_log table.

        This method records the processing of a Kafka message, including
        all metadata about the embedding and storage operations.

        Args:
            kafka_topic: The Kafka topic the message came from
            kafka_partition: The partition number
            kafka_offset: The message offset in the partition
            message_content: The message content (may be truncated)
            embedding_model: The OpenAI model used for embedding
            embedding_dimensions: The number of dimensions in the embedding
            opensearch_index: The OpenSearch index where the vector was stored
            opensearch_doc_id: The document ID in OpenSearch
            log_level: 'INFO' for success, 'ERROR' for failures
            error_message: Error details if processing failed
            processing_duration_ms: Total processing time in milliseconds

        Returns:
            A tuple of (id, timestamp) for the inserted log entry

        Raises:
            PostgresQueryError: If the insert fails
            PostgresConnectionError: If not connected
        """
        if not self.pool:
            raise PostgresConnectionError("Not connected to PostgreSQL")

        start_time = time.time()

        logger.debug(
            "Inserting log entry",
            kafka_topic=kafka_topic,
            kafka_partition=kafka_partition,
            kafka_offset=kafka_offset,
            log_level=log_level,
        )

        try:
            async with self.pool.acquire() as conn:
                # Use a transaction for the insert
                async with conn.transaction():
                    row = await conn.fetchrow(
                        INSERT_LOG_ENTRY,
                        kafka_topic,
                        kafka_partition,
                        kafka_offset,
                        message_content,
                        embedding_model,
                        embedding_dimensions,
                        opensearch_index,
                        opensearch_doc_id,
                        log_level,
                        error_message,
                        processing_duration_ms,
                    )

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Log entry inserted",
                log_id=row["id"],
                timestamp=str(row["timestamp"]),
                kafka_topic=kafka_topic,
                kafka_offset=kafka_offset,
                log_level=log_level,
                insert_duration_ms=duration_ms,
            )

            return row["id"], row["timestamp"]

        except asyncpg.PostgresError as e:
            logger.error(
                "Failed to insert log entry",
                error=str(e),
                kafka_topic=kafka_topic,
                kafka_offset=kafka_offset,
            )
            raise PostgresQueryError(
                f"Failed to insert log entry: {e}",
                details={
                    "kafka_topic": kafka_topic,
                    "kafka_offset": kafka_offset,
                },
            )

    async def close(self) -> None:
        """
        Close the PostgreSQL connection pool.

        This method should be called during graceful shutdown to properly
        release all database connections.
        """
        if self.pool:
            logger.info("Closing PostgreSQL connection pool...")
            await self.pool.close()
            self.pool = None
            self._connected = False
            logger.info("PostgreSQL connection pool closed")

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected to PostgreSQL."""
        return self._connected and self.pool is not None

    async def health_check(self) -> bool:
        """
        Check if the PostgreSQL connection is healthy.

        Returns:
            True if the connection is healthy, False otherwise
        """
        if not self.pool:
            return False

        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as e:
            logger.warning("PostgreSQL health check failed", error=str(e))
            return False
