"""
Kafka Consumer with AWS MSK IAM Authentication
==============================================

This module provides a Kafka consumer using confluent-kafka that supports:
- Traditional plaintext connections (for local development)
- AWS MSK IAM authentication via SASL_SSL (for production)

MSK IAM Authentication Flow:
---------------------------
When `kafka_use_iam_auth` is enabled:

1. The consumer uses SASL_SSL security protocol
2. The SASL mechanism is OAUTHBEARER with a custom token callback
3. The aws-msk-iam-sasl-signer library generates authentication tokens
4. Tokens are signed using AWS credentials from IRSA

Usage:
------
    from aws_connectivity_test.kafka_consumer import KafkaConsumerClient
    from aws_connectivity_test.config import get_settings

    async def handle_message(msg):
        print(f"Received: {msg.value().decode()}")

    async def main():
        settings = get_settings()
        consumer = KafkaConsumerClient(settings, handle_message)

        await consumer.connect()
        await consumer.consume()  # Runs until shutdown signal
        await consumer.close()
"""

import asyncio
import time
from typing import Any, Callable, Coroutine, Optional

from confluent_kafka import Consumer, KafkaError, KafkaException

from .config import Settings
from .exceptions import KafkaConnectionError, KafkaConsumerError
from .logging_config import get_logger

# Get a logger for this module
logger = get_logger(__name__)

# Type alias for the message handler callback
MessageHandler = Callable[[Any], Coroutine[Any, Any, None]]


class KafkaConsumerClient:
    """
    Kafka consumer with optional MSK IAM authentication using confluent-kafka.

    This client manages the Kafka consumer lifecycle, including:
    - Connection with appropriate authentication
    - Consumer group management
    - Message consumption with manual offset commit
    - Graceful shutdown handling

    Attributes:
        settings: Application settings containing Kafka configuration
        message_handler: Async callback to process each message
        consumer: confluent-kafka Consumer instance (None until connect())
        _running: Whether the consumer is running
    """

    def __init__(
        self,
        settings: Settings,
        message_handler: MessageHandler,
    ) -> None:
        """
        Initialize the Kafka consumer client.

        Args:
            settings: Application settings with Kafka configuration
            message_handler: Async function to process each message
        """
        self.settings = settings
        self.message_handler = message_handler
        self.consumer: Optional[Consumer] = None
        self._running = False
        self._consumer_task: Optional[asyncio.Task] = None

        # Log initialization
        logger.info(
            "Kafka consumer client initialized",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            topics=settings.kafka_topics_list,
            consumer_group=settings.kafka_consumer_group,
            security_protocol=settings.kafka_security_protocol,
            use_iam_auth=settings.kafka_use_iam_auth,
        )

    async def connect(self) -> None:
        """
        Connect to Kafka and subscribe to topics.

        This method:
        1. Configures the consumer with appropriate authentication
        2. Creates the Consumer instance
        3. Subscribes to configured topics

        Raises:
            KafkaConnectionError: If connection fails
        """
        start_time = time.time()
        logger.info("Connecting to Kafka...")

        try:
            # Build consumer configuration
            consumer_config = self._build_consumer_config()

            # Create the consumer
            logger.info(
                "Creating Kafka consumer",
                topics=self.settings.kafka_topics_list,
            )

            self.consumer = Consumer(consumer_config)

            # Subscribe to topics
            self.consumer.subscribe(self.settings.kafka_topics_list)

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Kafka consumer connected successfully",
                bootstrap_servers=self.settings.kafka_bootstrap_servers,
                topics=self.settings.kafka_topics_list,
                consumer_group=self.settings.kafka_consumer_group,
                duration_ms=duration_ms,
            )

        except KafkaException as e:
            logger.error(
                "Kafka connection failed",
                error=str(e),
                error_type=type(e).__name__,
                bootstrap_servers=self.settings.kafka_bootstrap_servers,
            )
            raise KafkaConnectionError(
                f"Failed to connect to Kafka: {e}",
                details={
                    "bootstrap_servers": self.settings.kafka_bootstrap_servers,
                    "topics": self.settings.kafka_topics_list,
                    "consumer_group": self.settings.kafka_consumer_group,
                },
            )
        except Exception as e:
            logger.error(
                "Unexpected error connecting to Kafka",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise KafkaConnectionError(f"Unexpected Kafka connection error: {e}")

    def _build_consumer_config(self) -> dict[str, Any]:
        """
        Build the Kafka consumer configuration dictionary.

        This method constructs the configuration based on settings,
        including authentication configuration for MSK IAM if enabled.

        Returns:
            Dictionary of consumer configuration options
        """
        # Base configuration that applies to all modes
        config: dict[str, Any] = {
            "bootstrap.servers": self.settings.kafka_bootstrap_servers,
            "group.id": self.settings.kafka_consumer_group,
            "auto.offset.reset": self.settings.kafka_auto_offset_reset,
            "enable.auto.commit": self.settings.kafka_enable_auto_commit,
            "session.timeout.ms": self.settings.kafka_session_timeout_ms,
            "max.poll.interval.ms": self.settings.kafka_max_poll_interval_ms,
            "security.protocol": self.settings.kafka_security_protocol,
        }

        # Configure authentication based on mode
        if self.settings.kafka_use_iam_auth:
            logger.info("Configuring MSK IAM authentication...")
            config.update(self._get_iam_auth_config())
        else:
            logger.info("Using plaintext connection (no authentication)")

        return config

    def _get_iam_auth_config(self) -> dict[str, Any]:
        """
        Get the configuration for MSK IAM authentication.

        This method configures SASL_SSL with OAUTHBEARER mechanism,
        using the aws-msk-iam-sasl-signer library for token generation.

        Returns:
            Dictionary of IAM authentication configuration
        """
        logger.debug(
            "Setting up MSK IAM authentication",
            region=self.settings.aws_region,
        )

        # Import the MSK IAM signer
        try:
            from aws_msk_iam_sasl_signer import MSKAuthTokenProvider
        except ImportError as e:
            logger.error(
                "aws-msk-iam-sasl-signer not installed",
                error=str(e),
            )
            raise KafkaConnectionError(
                "aws-msk-iam-sasl-signer is required for MSK IAM authentication. "
                "Install it with: pip install aws-msk-iam-sasl-signer-python"
            )

        # Capture the region for use in the callback
        aws_region = self.settings.aws_region

        # Define the OAuth token callback for confluent-kafka
        def oauth_cb(oauth_config: str) -> tuple[str, float]:
            """
            Callback to generate a new OAuth token for MSK IAM auth.

            This callback is invoked by confluent-kafka when:
            - Initially connecting to the broker
            - The current token is about to expire

            Args:
                oauth_config: OAuth configuration string (unused for MSK IAM)

            Returns:
                Tuple of (token, expiry_time_in_seconds)
            """
            logger.debug("Generating MSK IAM authentication token...")
            try:
                # Generate a signed token using AWS credentials
                token, expiry_ms = MSKAuthTokenProvider.generate_auth_token(
                    region=aws_region
                )
                logger.debug(
                    "MSK IAM token generated",
                    token_length=len(token),
                    expires_in_ms=expiry_ms,
                )
                return token, expiry_ms / 1000.0
            except Exception as e:
                logger.error(
                    "Failed to generate MSK IAM token",
                    error=str(e),
                )
                raise

        logger.info("MSK IAM authentication configured")

        return {
            "sasl.mechanism": "OAUTHBEARER",
            "oauth_cb": oauth_cb,
        }

    async def consume(self) -> None:
        """
        Start consuming messages from Kafka.

        This method runs an infinite loop that:
        1. Polls for messages from subscribed topics
        2. Calls the message handler for each message
        3. Commits the offset after successful processing

        The loop continues until shutdown is signaled via stop().

        Raises:
            KafkaConsumerError: If consumption fails unexpectedly
        """
        if not self.consumer:
            raise KafkaConsumerError("Consumer not connected")

        self._running = True
        messages_processed = 0

        logger.info(
            "Starting message consumption",
            topics=self.settings.kafka_topics_list,
            consumer_group=self.settings.kafka_consumer_group,
        )

        try:
            # Main consumption loop
            while self._running:
                # Run the synchronous poll in a thread pool
                msg = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.consumer.poll(timeout=1.0)
                )

                if msg is None:
                    # No message available
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        # End of partition - not an error
                        logger.debug(
                            "Reached end of partition",
                            topic=msg.topic(),
                            partition=msg.partition(),
                        )
                        continue
                    else:
                        # Log as warning since UNKNOWN_TOPIC_OR_PART can be transient
                        # during metadata refresh with IAM authentication
                        logger.warning(
                            "Kafka consumer error",
                            error=str(msg.error()),
                            topic=msg.topic() if msg.topic() else "unknown",
                        )
                        continue

                # Process the message
                await self._process_message(msg)
                messages_processed += 1

                # Commit offsets manually if auto-commit is disabled
                if not self.settings.kafka_enable_auto_commit:
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.consumer.commit
                    )

        except asyncio.CancelledError:
            logger.info("Consumption cancelled")

        except Exception as e:
            logger.error(
                "Unexpected error during consumption",
                error=str(e),
                error_type=type(e).__name__,
                messages_processed=messages_processed,
            )
            raise KafkaConsumerError(f"Unexpected consumer error: {e}")

        finally:
            logger.info(
                "Message consumption stopped",
                messages_processed=messages_processed,
            )
            self._running = False

    async def _process_message(self, msg: Any) -> None:
        """
        Process a single Kafka message.

        This method logs the message metadata and calls the message handler.
        Errors in the handler are logged but don't stop consumption.

        Args:
            msg: The Kafka message from confluent-kafka
        """
        start_time = time.time()

        logger.info(
            "Processing message",
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
            key=msg.key().decode("utf-8") if msg.key() else None,
            value_size=len(msg.value()) if msg.value() else 0,
            timestamp=msg.timestamp()[1] if msg.timestamp() else None,
        )

        try:
            # Call the message handler
            await self.message_handler(msg)

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Message processed successfully",
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Failed to process message",
                error=str(e),
                error_type=type(e).__name__,
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
                duration_ms=duration_ms,
            )
            # Re-raise to prevent offset commit for failed messages
            raise

    async def stop(self) -> None:
        """
        Signal the consumer to stop gracefully.

        This method sets the running flag to False, which will cause
        the consumption loop to exit after completing the current poll.
        """
        logger.info("Stopping Kafka consumer...")
        self._running = False

    async def close(self) -> None:
        """
        Close the Kafka consumer and release resources.

        This method should be called during graceful shutdown to:
        1. Commit any pending offsets
        2. Leave the consumer group cleanly
        3. Close network connections
        """
        if self.consumer:
            logger.info("Closing Kafka consumer...")

            # Stop consumption if still running
            if self._running:
                await self.stop()

            # Close the consumer in a thread pool (it's synchronous)
            await asyncio.get_event_loop().run_in_executor(
                None, self.consumer.close
            )
            self.consumer = None

            logger.info("Kafka consumer closed")

    @property
    def is_connected(self) -> bool:
        """Check if the consumer is connected to Kafka."""
        return self.consumer is not None

    @property
    def is_running(self) -> bool:
        """Check if the consumer is actively consuming."""
        return self._running

    async def health_check(self) -> bool:
        """
        Check if the Kafka consumer is healthy.

        Returns:
            True if the consumer is connected, False otherwise
        """
        if not self.consumer:
            return False

        try:
            # Try to get cluster metadata as a health check
            metadata = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.consumer.list_topics(timeout=5.0)
            )
            return metadata is not None
        except Exception as e:
            logger.warning("Kafka health check failed", error=str(e))
            return False
