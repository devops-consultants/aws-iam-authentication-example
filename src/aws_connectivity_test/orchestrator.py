"""
Service Orchestrator for AWS Connectivity Test
==============================================

This module coordinates all service components and manages the message
processing pipeline. It handles:
- Service initialization in the correct order
- Message processing pipeline execution
- Concurrent processing with limits
- Error handling and logging
- Graceful shutdown coordination

Startup Sequence:
----------------
Services are initialized in this order to ensure dependencies are ready:

1. PostgreSQL (creates demo_log table)
2. OpenSearch (validates index exists)
3. OpenAI (initializes embedding client)
4. Kafka (connects consumer, starts consuming)

This order ensures:
- Database is ready before logging operations
- OpenSearch is ready before storing vectors
- OpenAI is ready before generating embeddings
- Kafka starts last since it triggers the entire pipeline

Message Processing Pipeline:
---------------------------
For each Kafka message, the pipeline executes these steps:

    ┌─────────────────┐
    │ Kafka Message   │
    │ (consumed)      │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Generate        │
    │ Embedding       │
    │ (OpenAI)        │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Store Vector    │
    │ (OpenSearch)    │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Log Operation   │
    │ (PostgreSQL)    │
    └────────┬────────┘
             │
             ▼
         Complete

Concurrent Processing:
---------------------
Messages can be processed concurrently up to a configurable limit.
This improves throughput while preventing resource exhaustion.

Usage:
------
    from aws_connectivity_test.orchestrator import Orchestrator
    from aws_connectivity_test.config import get_settings

    async def main():
        settings = get_settings()
        orchestrator = Orchestrator(settings)

        await orchestrator.startup()
        await orchestrator.run()  # Runs until shutdown signal
        await orchestrator.shutdown()
"""

import asyncio
import time
from typing import Any, Optional

from .config import Settings
from .exceptions import (
    PipelineError,
    StartupError,
)
from .kafka_consumer import KafkaConsumerClient
from .kafka_producer import KafkaProducerClient
from .logging_config import get_logger
from .openai_client import OpenAIClient
from .opensearch_client import OpenSearchClient
from .postgres_client import PostgresClient
from .redis_client import RedisClient

# Get a logger for this module
logger = get_logger(__name__)


class Orchestrator:
    """
    Coordinates all service components and manages the message pipeline.

    This class is the central coordinator that:
    - Manages the lifecycle of all service clients
    - Processes Kafka messages through the full pipeline
    - Handles errors and logs all operations
    - Coordinates graceful shutdown
    - Tracks processing status in Redis
    - Provides message publishing capability for end-to-end testing

    Attributes:
        settings: Application settings
        postgres: PostgreSQL client instance
        opensearch: OpenSearch client instance
        openai: OpenAI client instance
        kafka: Kafka consumer client instance
        producer: Kafka producer client instance
        redis: Redis client instance for status tracking
        _running: Whether the orchestrator is running
        _healthy: Whether all services are healthy
        _startup_complete: Whether startup has completed
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the orchestrator with all service clients.

        Args:
            settings: Application settings
        """
        self.settings = settings

        # ---------------------------------------------------------------
        # Create service clients
        # ---------------------------------------------------------------
        # Each client is created but not connected yet
        # Connection happens in startup() in the correct order
        # ---------------------------------------------------------------
        self.postgres = PostgresClient(settings)
        self.opensearch = OpenSearchClient(settings)
        self.openai = OpenAIClient(settings)
        self.redis = RedisClient(settings)
        self.producer = KafkaProducerClient(settings)

        # Kafka consumer is created with our message handler
        self.kafka = KafkaConsumerClient(
            settings,
            message_handler=self._handle_message,
        )

        # State tracking
        self._running = False
        self._healthy = False
        self._startup_complete = False

        # Concurrency control
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_messages)
        self._processing_count = 0

        logger.info(
            "Orchestrator initialized",
            service=settings.service_name,
            version=settings.service_version,
            max_concurrent_messages=settings.max_concurrent_messages,
        )

    async def startup(self) -> None:
        """
        Initialize all services in the correct order.

        This method connects to all AWS services and validates connectivity.
        The order ensures dependencies are ready before dependents.

        Raises:
            StartupError: If any service fails to initialize
        """
        start_time = time.time()

        logger.info(
            "="*60,
        )
        logger.info(
            "STARTING AWS CONNECTIVITY TEST SERVICE",
            service=self.settings.service_name,
            version=self.settings.service_version,
        )
        logger.info(
            "="*60,
        )

        # Log configuration summary (with sensitive values masked)
        logger.info(
            "Configuration summary",
            kafka_bootstrap_servers=self.settings.kafka_bootstrap_servers,
            kafka_topics=self.settings.kafka_topics_list,
            kafka_consumer_group=self.settings.kafka_consumer_group,
            kafka_use_iam_auth=self.settings.kafka_use_iam_auth,
            postgres_host=self.settings.postgres_host,
            postgresql_use_iam_auth=self.settings.postgresql_use_iam_auth,
            opensearch_enabled=self.settings.opensearch_enabled,
            opensearch_use_iam_auth=self.settings.opensearch_use_iam_auth,
            openai_enabled=self.settings.openai_enabled,
            openai_model=self.settings.openai_embedding_model,
            redis_enabled=self.settings.redis_enabled,
            redis_host=self.settings.redis_host,
            redis_use_iam_auth=self.settings.redis_use_iam_auth,
            aws_region=self.settings.aws_region,
        )

        try:
            # ---------------------------------------------------------------
            # Step 1: Connect to PostgreSQL
            # ---------------------------------------------------------------
            logger.info("-"*40)
            logger.info("Step 1/4: Connecting to PostgreSQL...")
            logger.info("-"*40)
            await self.postgres.connect()
            logger.info("✓ PostgreSQL connection successful")

            # ---------------------------------------------------------------
            # Step 2: Connect to OpenSearch
            # ---------------------------------------------------------------
            logger.info("-"*40)
            logger.info("Step 2/4: Connecting to OpenSearch...")
            logger.info("-"*40)
            await self.opensearch.connect()
            logger.info("✓ OpenSearch connection successful")

            # ---------------------------------------------------------------
            # Step 3: Initialize OpenAI
            # ---------------------------------------------------------------
            logger.info("-"*40)
            logger.info("Step 3/4: Initializing OpenAI...")
            logger.info("-"*40)
            await self.openai.initialize()
            logger.info("✓ OpenAI initialization successful")

            # ---------------------------------------------------------------
            # Step 4: Connect to Kafka Consumer
            # ---------------------------------------------------------------
            logger.info("-"*40)
            logger.info("Step 4/6: Connecting to Kafka consumer...")
            logger.info("-"*40)
            await self.kafka.connect()
            logger.info("✓ Kafka consumer connection successful")

            # ---------------------------------------------------------------
            # Step 5: Connect to Redis (for status tracking)
            # ---------------------------------------------------------------
            logger.info("-"*40)
            logger.info("Step 5/6: Connecting to Redis...")
            logger.info("-"*40)
            await self.redis.connect()
            logger.info("✓ Redis connection successful")

            # ---------------------------------------------------------------
            # Step 6: Connect to Kafka Producer (for publishing)
            # ---------------------------------------------------------------
            logger.info("-"*40)
            logger.info("Step 6/6: Connecting to Kafka producer...")
            logger.info("-"*40)
            await self.producer.connect()
            logger.info("✓ Kafka producer connection successful")

            # ---------------------------------------------------------------
            # Startup complete
            # ---------------------------------------------------------------
            self._startup_complete = True
            self._healthy = True

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info("="*60)
            logger.info(
                "STARTUP COMPLETE - ALL SERVICES CONNECTED",
                duration_ms=duration_ms,
            )
            logger.info("="*60)

        except Exception as e:
            logger.error(
                "STARTUP FAILED",
                error=str(e),
                error_type=type(e).__name__,
                duration_ms=int((time.time() - start_time) * 1000),
            )
            self._healthy = False
            raise StartupError(
                f"Service startup failed: {e}",
                details={"component": type(e).__name__},
            )

    async def run(self) -> None:
        """
        Start the main processing loop.

        This method starts the Kafka consumer which will call our message
        handler for each message. It runs until shutdown() is called.
        """
        if not self._startup_complete:
            raise StartupError("Cannot run - startup not complete")

        self._running = True

        logger.info(
            "Starting message consumption...",
            topics=self.settings.kafka_topics_list,
        )

        try:
            # Start consuming messages
            # This blocks until stop() is called or an error occurs
            await self.kafka.consume()

        except asyncio.CancelledError:
            logger.info("Processing loop cancelled")

        except Exception as e:
            logger.error(
                "Processing loop error",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

        finally:
            self._running = False

    async def shutdown(self) -> None:
        """
        Gracefully shut down all services.

        This method stops the Kafka consumer and closes all service
        connections in reverse order of initialization.
        """
        logger.info("="*60)
        logger.info("SHUTTING DOWN AWS CONNECTIVITY TEST SERVICE")
        logger.info("="*60)

        start_time = time.time()

        # Wait for in-flight messages to complete
        if self._processing_count > 0:
            logger.info(
                "Waiting for in-flight messages to complete",
                count=self._processing_count,
            )
            # Wait up to shutdown_timeout for messages to complete
            wait_time = 0
            while self._processing_count > 0 and wait_time < self.settings.shutdown_timeout:
                await asyncio.sleep(0.5)
                wait_time += 0.5

        # Stop services in reverse order
        try:
            logger.info("Stopping Kafka producer...")
            await self.producer.close()
            logger.info("✓ Kafka producer stopped")

            logger.info("Closing Redis connection...")
            await self.redis.close()
            logger.info("✓ Redis connection closed")

            logger.info("Stopping Kafka consumer...")
            await self.kafka.close()
            logger.info("✓ Kafka consumer stopped")

            logger.info("Closing OpenAI client...")
            await self.openai.close()
            logger.info("✓ OpenAI client closed")

            logger.info("Closing OpenSearch client...")
            await self.opensearch.close()
            logger.info("✓ OpenSearch client closed")

            logger.info("Closing PostgreSQL connection...")
            await self.postgres.close()
            logger.info("✓ PostgreSQL connection closed")

        except Exception as e:
            logger.error(
                "Error during shutdown",
                error=str(e),
                error_type=type(e).__name__,
            )

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "="*60,
        )
        logger.info(
            "SHUTDOWN COMPLETE",
            duration_ms=duration_ms,
        )
        logger.info(
            "="*60,
        )

    async def _handle_message(self, msg: Any) -> None:
        """
        Process a single Kafka message through the full pipeline.

        This method is called by the Kafka consumer for each message.
        It executes the full pipeline: consume → embed → store → log.
        Status is tracked in Redis at each stage for monitoring.

        Args:
            msg: The Kafka message from confluent-kafka
        """
        # Use semaphore to limit concurrent processing
        async with self._semaphore:
            self._processing_count += 1

            pipeline_start = time.time()

            # Extract message metadata
            # Note: confluent-kafka uses methods, not properties
            topic = msg.topic()
            partition = msg.partition()
            offset = msg.offset()
            value = msg.value().decode("utf-8") if msg.value() else ""

            # Extract message_id from headers if present (set by publisher)
            # Otherwise fall back to topic-partition-offset format
            message_id = None
            headers = msg.headers()
            if headers:
                for key, val in headers:
                    if key == "message_id" and val:
                        message_id = val.decode("utf-8") if isinstance(val, bytes) else val
                        break

            # Use topic-partition-offset as fallback if no header
            if not message_id:
                message_id = f"{topic}-{partition}-{offset}"

            logger.info(
                "Starting message pipeline",
                kafka_topic=topic,
                kafka_partition=partition,
                kafka_offset=offset,
                message_id=message_id,
                message_length=len(value),
            )

            # Track timing for each step
            timings: dict[str, int] = {}
            error_message: Optional[str] = None
            embedding: list[float] = []
            doc_id: str = ""

            try:
                # ---------------------------------------------------------------
                # Status: kafka_consumed
                # ---------------------------------------------------------------
                await self.redis.set_status(
                    message_id=message_id,
                    stage="kafka_consumed",
                    details={
                        "topic": topic,
                        "partition": partition,
                        "offset": offset,
                        "message_length": len(value),
                    },
                )

                # ---------------------------------------------------------------
                # Step 1: Generate embedding with OpenAI
                # ---------------------------------------------------------------
                step_start = time.time()
                logger.debug(
                    "Pipeline step 1: Generating embedding",
                    kafka_offset=offset,
                )

                if self.settings.openai_enabled and value:
                    embedding = await self.openai.generate_embedding(value)
                    timings["embedding_ms"] = int((time.time() - step_start) * 1000)
                    logger.debug(
                        "Embedding generated",
                        dimensions=len(embedding),
                        duration_ms=timings["embedding_ms"],
                    )

                    # Status: embedding_generated
                    await self.redis.set_status(
                        message_id=message_id,
                        stage="embedding_generated",
                        details={
                            "dimensions": len(embedding),
                            "model": self.settings.openai_embedding_model,
                            "duration_ms": timings["embedding_ms"],
                        },
                    )
                else:
                    timings["embedding_ms"] = 0
                    logger.debug("Embedding skipped (disabled or empty message)")

                # ---------------------------------------------------------------
                # Step 2: Store vector in OpenSearch
                # ---------------------------------------------------------------
                step_start = time.time()
                logger.debug(
                    "Pipeline step 2: Storing vector in OpenSearch",
                    kafka_offset=offset,
                )

                if self.settings.opensearch_enabled and embedding:
                    doc_id = await self.opensearch.write_vector(
                        vector=embedding,
                        kafka_topic=topic,
                        kafka_partition=partition,
                        kafka_offset=offset,
                        message_preview=value[:200] if value else None,
                    )
                    timings["opensearch_ms"] = int((time.time() - step_start) * 1000)
                    logger.debug(
                        "Vector stored in OpenSearch",
                        doc_id=doc_id,
                        duration_ms=timings["opensearch_ms"],
                    )

                    # Status: opensearch_inserted
                    await self.redis.set_status(
                        message_id=message_id,
                        stage="opensearch_inserted",
                        details={
                            "doc_id": doc_id,
                            "index": self.settings.opensearch_index,
                            "duration_ms": timings["opensearch_ms"],
                        },
                    )
                else:
                    timings["opensearch_ms"] = 0
                    doc_id = "skipped"
                    logger.debug("OpenSearch write skipped (disabled or no embedding)")

                # ---------------------------------------------------------------
                # Step 3: Log to PostgreSQL
                # ---------------------------------------------------------------
                step_start = time.time()
                logger.debug(
                    "Pipeline step 3: Logging to PostgreSQL",
                    kafka_offset=offset,
                )

                total_duration = int((time.time() - pipeline_start) * 1000)

                await self.postgres.insert_log_entry(
                    kafka_topic=topic,
                    kafka_partition=partition,
                    kafka_offset=offset,
                    message_content=value[:1000] if value else None,
                    embedding_model=self.settings.openai_embedding_model if embedding else None,
                    embedding_dimensions=len(embedding) if embedding else None,
                    opensearch_index=self.settings.opensearch_index if doc_id != "skipped" else None,
                    opensearch_doc_id=doc_id if doc_id != "skipped" else None,
                    log_level="INFO",
                    processing_duration_ms=total_duration,
                )

                timings["postgres_ms"] = int((time.time() - step_start) * 1000)

                # Status: postgres_logged
                await self.redis.set_status(
                    message_id=message_id,
                    stage="postgres_logged",
                    details={
                        "success": True,
                        "duration_ms": timings["postgres_ms"],
                    },
                )

                # ---------------------------------------------------------------
                # Pipeline complete
                # ---------------------------------------------------------------
                total_duration = int((time.time() - pipeline_start) * 1000)

                logger.info(
                    "Message pipeline complete",
                    kafka_topic=topic,
                    kafka_partition=partition,
                    kafka_offset=offset,
                    message_id=message_id,
                    embedding_dimensions=len(embedding) if embedding else 0,
                    opensearch_doc_id=doc_id,
                    total_duration_ms=total_duration,
                    embedding_ms=timings.get("embedding_ms", 0),
                    opensearch_ms=timings.get("opensearch_ms", 0),
                    postgres_ms=timings.get("postgres_ms", 0),
                )

            except Exception as e:
                # ---------------------------------------------------------------
                # Handle pipeline errors
                # ---------------------------------------------------------------
                error_message = str(e)
                total_duration = int((time.time() - pipeline_start) * 1000)

                logger.error(
                    "Message pipeline failed",
                    error=error_message,
                    error_type=type(e).__name__,
                    kafka_topic=topic,
                    kafka_partition=partition,
                    kafka_offset=offset,
                    message_id=message_id,
                    total_duration_ms=total_duration,
                )

                # Update Redis status with error
                try:
                    await self.redis.set_status(
                        message_id=message_id,
                        stage="failed",
                        details={"duration_ms": total_duration},
                        error=error_message,
                    )
                except Exception as redis_error:
                    logger.warning(
                        "Failed to update Redis status with error",
                        error=str(redis_error),
                    )

                # Log the error to PostgreSQL
                try:
                    await self.postgres.insert_log_entry(
                        kafka_topic=topic,
                        kafka_partition=partition,
                        kafka_offset=offset,
                        message_content=value[:1000] if value else None,
                        log_level="ERROR",
                        error_message=error_message,
                        processing_duration_ms=total_duration,
                    )
                except Exception as log_error:
                    logger.error(
                        "Failed to log error to PostgreSQL",
                        error=str(log_error),
                    )

                # Re-raise to prevent offset commit
                raise PipelineError(
                    f"Pipeline failed at step: {e}",
                    details={
                        "kafka_topic": topic,
                        "kafka_offset": offset,
                        "message_id": message_id,
                        "error": error_message,
                    },
                )

            finally:
                self._processing_count -= 1

    # =========================================================================
    # Publishing and Status Methods
    # =========================================================================

    async def publish_message(self, content: str, key: Optional[str] = None) -> str:
        """
        Publish a message to Kafka for end-to-end testing.

        This method allows publishing test messages via the API, enabling
        end-to-end testing of the full pipeline from publish to consumption.

        Args:
            content: Message content to publish
            key: Optional message key for partitioning

        Returns:
            Message ID (UUID) for status tracking

        Raises:
            KafkaPublishError: If publishing fails
        """
        # Use the first configured topic for publishing
        topic = self.settings.kafka_topics_list[0]

        logger.info(
            "Publishing test message",
            topic=topic,
            content_length=len(content),
            has_key=key is not None,
        )

        message_id = await self.producer.publish(
            topic=topic,
            message=content,
            key=key,
        )

        # Set initial status in Redis
        await self.redis.set_status(
            message_id=message_id,
            stage="published",
            details={
                "topic": topic,
                "content_length": len(content),
            },
        )

        logger.info(
            "Test message published",
            message_id=message_id,
            topic=topic,
        )

        return message_id

    async def get_processing_status(
        self,
        message_id: Optional[str] = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Get processing status from Redis.

        Args:
            message_id: Specific message ID to get status for (optional)
            limit: Maximum number of statuses to return if no message_id

        Returns:
            Status dict for single message, or list of statuses
        """
        if message_id:
            status = await self.redis.get_status(message_id)
            return {
                "message_id": message_id,
                "found": status is not None,
                "status": status,
            }
        else:
            statuses = await self.redis.get_all_statuses(limit=limit)
            return {
                "count": len(statuses),
                "statuses": statuses,
            }

    @property
    def is_healthy(self) -> bool:
        """Check if all services are healthy."""
        return self._healthy

    @property
    def is_running(self) -> bool:
        """Check if the orchestrator is running."""
        return self._running

    async def health_check(self) -> dict[str, Any]:
        """
        Perform a health check on all services.

        Returns:
            Dictionary with health status for each service
        """
        results: dict[str, Any] = {
            "healthy": True,
            "services": {},
        }

        # Check PostgreSQL
        postgres_healthy = await self.postgres.health_check()
        results["services"]["postgresql"] = {
            "healthy": postgres_healthy,
            "connected": self.postgres.is_connected,
        }
        if not postgres_healthy:
            results["healthy"] = False

        # Check OpenSearch
        opensearch_healthy = await self.opensearch.health_check()
        results["services"]["opensearch"] = {
            "healthy": opensearch_healthy,
            "connected": self.opensearch.is_connected,
            "enabled": self.settings.opensearch_enabled,
        }
        if not opensearch_healthy and self.settings.opensearch_enabled:
            results["healthy"] = False

        # Check OpenAI
        openai_healthy = await self.openai.health_check()
        results["services"]["openai"] = {
            "healthy": openai_healthy,
            "initialized": self.openai.is_initialized,
            "enabled": self.settings.openai_enabled,
        }
        if not openai_healthy and self.settings.openai_enabled:
            results["healthy"] = False

        # Check Kafka consumer
        kafka_healthy = await self.kafka.health_check()
        results["services"]["kafka"] = {
            "healthy": kafka_healthy,
            "connected": self.kafka.is_connected,
            "running": self.kafka.is_running,
        }
        if not kafka_healthy:
            results["healthy"] = False

        # Check Redis
        redis_healthy = await self.redis.health_check()
        results["services"]["redis"] = {
            "healthy": redis_healthy,
            "connected": self.redis.is_connected,
            "enabled": self.settings.redis_enabled,
        }
        if not redis_healthy and self.settings.redis_enabled:
            results["healthy"] = False

        # Check Kafka producer (non-critical - don't fail overall health)
        producer_healthy = await self.producer.health_check()
        results["services"]["kafka_producer"] = {
            "healthy": producer_healthy,
            "connected": self.producer.is_connected,
        }
        # Note: Producer is optional functionality for /publish endpoint
        # Don't fail overall health if producer has issues

        return results
