"""
Kafka Producer with AWS MSK IAM Authentication
==============================================

This module provides a Kafka producer using confluent-kafka that supports:
- Traditional plaintext connections (for local development)
- AWS MSK IAM authentication via SASL_SSL (for production)

MSK IAM Authentication Flow:
---------------------------
When `kafka_use_iam_auth` is enabled:

1. The producer uses SASL_SSL security protocol
2. The SASL mechanism is OAUTHBEARER with a custom token callback
3. The aws-msk-iam-sasl-signer library generates authentication tokens
4. Tokens are signed using AWS credentials from IRSA

This follows the same authentication pattern as the Kafka consumer
to maintain consistency across the codebase.

Message Publishing:
------------------
The producer supports:
- Synchronous publish with delivery confirmation
- Configurable key and value serialization
- Delivery callback for logging and monitoring

Usage:
------
    from aws_connectivity_test.kafka_producer import KafkaProducerClient
    from aws_connectivity_test.config import get_settings

    async def main():
        settings = get_settings()
        producer = KafkaProducerClient(settings)

        await producer.connect()

        # Publish a message
        message_id = await producer.publish(
            topic="test-topic",
            message="Hello, Kafka!",
            key="optional-key"
        )

        await producer.close()
"""

import asyncio
import time
import uuid
from typing import Any, Optional

from confluent_kafka import KafkaException, Producer

from .config import Settings
from .exceptions import KafkaConnectionError, KafkaProducerError, KafkaPublishError
from .logging_config import get_logger

# Get a logger for this module
logger = get_logger(__name__)


class KafkaProducerClient:
    """
    Kafka producer with optional MSK IAM authentication using confluent-kafka.

    This client manages the Kafka producer lifecycle, including:
    - Connection with appropriate authentication
    - Message publishing with delivery confirmation
    - Graceful shutdown handling

    The producer uses the same MSK IAM authentication pattern as the consumer
    for consistency. Tokens are generated using the aws-msk-iam-sasl-signer
    library and are automatically refreshed by confluent-kafka.

    Attributes:
        settings: Application settings containing Kafka configuration
        producer: confluent-kafka Producer instance (None until connect())
        _connected: Whether the producer is connected
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the Kafka producer client.

        Args:
            settings: Application settings with Kafka configuration
        """
        self.settings = settings
        self.producer: Optional[Producer] = None
        self._connected = False

        # Log initialization
        logger.info(
            "Kafka producer client initialized",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            security_protocol=settings.kafka_security_protocol,
            use_iam_auth=settings.kafka_use_iam_auth,
        )

    async def connect(self) -> None:
        """
        Connect to Kafka as a producer.

        This method:
        1. Configures the producer with appropriate authentication
        2. Creates the Producer instance
        3. Validates connectivity (implicit in first produce)

        Raises:
            KafkaConnectionError: If connection fails
        """
        start_time = time.time()
        logger.info("Connecting Kafka producer...")

        try:
            # Build producer configuration
            producer_config = self._build_producer_config()

            # Create the producer
            logger.info("Creating Kafka producer...")
            self.producer = Producer(producer_config)

            self._connected = True
            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Kafka producer connected successfully",
                bootstrap_servers=self.settings.kafka_bootstrap_servers,
                duration_ms=duration_ms,
            )

        except KafkaException as e:
            logger.error(
                "Kafka producer connection failed",
                error=str(e),
                error_type=type(e).__name__,
                bootstrap_servers=self.settings.kafka_bootstrap_servers,
            )
            raise KafkaConnectionError(
                f"Failed to create Kafka producer: {e}",
                details={"bootstrap_servers": self.settings.kafka_bootstrap_servers},
            )
        except Exception as e:
            logger.error(
                "Unexpected error connecting Kafka producer",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise KafkaConnectionError(f"Unexpected Kafka producer error: {e}")

    def _build_producer_config(self) -> dict[str, Any]:
        """
        Build the Kafka producer configuration dictionary.

        This method constructs the configuration based on settings,
        including authentication configuration for MSK IAM if enabled.

        Returns:
            Dictionary of producer configuration options
        """
        # Base configuration that applies to all modes
        config: dict[str, Any] = {
            "bootstrap.servers": self.settings.kafka_bootstrap_servers,
            "security.protocol": self.settings.kafka_security_protocol,
            # Producer-specific settings
            "acks": "all",  # Wait for all replicas to acknowledge
            "retries": 3,  # Number of retries on failure
            "retry.backoff.ms": 100,  # Backoff between retries
            "delivery.timeout.ms": 30000,  # Total time for delivery (30s)
            "request.timeout.ms": 10000,  # Request timeout (10s)
            "linger.ms": 5,  # Small delay to batch messages
        }

        # Configure authentication based on mode
        if self.settings.kafka_use_iam_auth:
            logger.info("Configuring MSK IAM authentication for producer...")
            config.update(self._get_iam_auth_config())
        else:
            logger.info("Using plaintext connection (no authentication)")

        return config

    def _get_iam_auth_config(self) -> dict[str, Any]:
        """
        Get the configuration for MSK IAM authentication.

        This method configures SASL_SSL with OAUTHBEARER mechanism,
        using the aws-msk-iam-sasl-signer library for token generation.

        This is identical to the consumer's IAM auth configuration to
        ensure consistency across the codebase.

        Returns:
            Dictionary of IAM authentication configuration
        """
        logger.debug(
            "Setting up MSK IAM authentication for producer",
            region=self.settings.aws_region,
        )

        # Import the MSK IAM signer
        # This library generates signed authentication tokens using AWS credentials
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

        # Capture the region for use in the callback closure
        aws_region = self.settings.aws_region

        def oauth_cb(oauth_config: str) -> tuple[str, float]:
            """
            Callback to generate a new OAuth token for MSK IAM auth.

            This callback is invoked by confluent-kafka when:
            - Initially connecting to the broker
            - The current token is about to expire

            How it works:
            1. The MSKAuthTokenProvider uses boto3/botocore to get AWS credentials
            2. It generates a signed authentication token using SigV4
            3. The token and expiry time are returned to confluent-kafka
            4. confluent-kafka uses the token for SASL OAUTHBEARER authentication

            The credentials come from IRSA (IAM Roles for Service Accounts) when
            running in Kubernetes, or from the default credential chain locally.

            Args:
                oauth_config: OAuth configuration string (unused for MSK IAM)

            Returns:
                Tuple of (token, expiry_time_in_seconds)
            """
            logger.debug("Generating MSK IAM authentication token for producer...")
            try:
                # Generate a signed token using AWS credentials
                # The token is valid for 15 minutes by default
                token, expiry_ms = MSKAuthTokenProvider.generate_auth_token(
                    region=aws_region
                )
                logger.debug(
                    "MSK IAM token generated for producer",
                    token_length=len(token),
                    expires_in_ms=expiry_ms,
                )
                # Return token and expiry time in seconds
                return token, expiry_ms / 1000.0
            except Exception as e:
                logger.error(
                    "Failed to generate MSK IAM token for producer",
                    error=str(e),
                )
                raise

        logger.info("MSK IAM authentication configured for producer")

        return {
            "sasl.mechanism": "OAUTHBEARER",
            "oauth_cb": oauth_cb,
        }

    async def publish(
        self,
        topic: str,
        message: str,
        key: Optional[str] = None,
    ) -> str:
        """
        Publish a message to a Kafka topic.

        This method:
        1. Generates a message ID for tracking
        2. Publishes the message to Kafka
        3. Waits for delivery confirmation
        4. Returns the message ID for status tracking

        Args:
            topic: Kafka topic to publish to
            message: Message content (will be UTF-8 encoded)
            key: Optional message key for partitioning

        Returns:
            Message ID (UUID) for tracking

        Raises:
            KafkaPublishError: If publishing fails
        """
        if not self.producer:
            raise KafkaProducerError("Producer not connected")

        # Generate a unique message ID for tracking
        message_id = str(uuid.uuid4())
        start_time = time.time()

        logger.info(
            "Publishing message to Kafka",
            topic=topic,
            message_id=message_id,
            message_length=len(message),
            has_key=key is not None,
        )

        # Track delivery status
        delivery_error: Optional[Exception] = None
        delivered_offset: Optional[int] = None
        delivered_partition: Optional[int] = None

        def delivery_callback(err: Any, msg: Any) -> None:
            """
            Callback invoked when message delivery completes or fails.

            This callback is called by confluent-kafka when the broker
            acknowledges the message or when delivery fails.

            Args:
                err: Error object if delivery failed, None on success
                msg: Message object with metadata
            """
            nonlocal delivery_error, delivered_offset, delivered_partition

            if err is not None:
                # Delivery failed
                delivery_error = err
                logger.error(
                    "Message delivery failed",
                    error=str(err),
                    topic=msg.topic() if msg else topic,
                    message_id=message_id,
                )
            else:
                # Delivery successful
                delivered_offset = msg.offset()
                delivered_partition = msg.partition()
                logger.debug(
                    "Message delivered successfully",
                    topic=msg.topic(),
                    partition=delivered_partition,
                    offset=delivered_offset,
                    message_id=message_id,
                )

        try:
            # Produce the message
            # The key and value are encoded as bytes
            self.producer.produce(
                topic=topic,
                value=message.encode("utf-8"),
                key=key.encode("utf-8") if key else None,
                callback=delivery_callback,
                headers={"message_id": message_id},
            )

            # Flush to ensure delivery
            # This waits for delivery confirmation or timeout
            # Run in executor since flush() is blocking
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.producer.flush(timeout=10.0),
            )

            # Check if delivery succeeded
            if delivery_error is not None:
                raise KafkaPublishError(
                    f"Message delivery failed: {delivery_error}",
                    details={
                        "topic": topic,
                        "message_id": message_id,
                        "error": str(delivery_error),
                    },
                )

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Message published successfully",
                topic=topic,
                message_id=message_id,
                partition=delivered_partition,
                offset=delivered_offset,
                duration_ms=duration_ms,
            )

            return message_id

        except KafkaPublishError:
            raise
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Failed to publish message",
                error=str(e),
                error_type=type(e).__name__,
                topic=topic,
                message_id=message_id,
                duration_ms=duration_ms,
            )
            raise KafkaPublishError(
                f"Failed to publish message to {topic}: {e}",
                details={"topic": topic, "message_id": message_id},
            )

    async def close(self) -> None:
        """
        Close the Kafka producer and release resources.

        This method should be called during graceful shutdown to:
        1. Flush any pending messages
        2. Close the producer cleanly
        """
        if self.producer:
            logger.info("Closing Kafka producer...")

            # Flush any pending messages
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.producer.flush(timeout=10.0),
                )
            except Exception as e:
                logger.warning(
                    "Error flushing producer during close",
                    error=str(e),
                )

            self.producer = None
            self._connected = False

            logger.info("Kafka producer closed")

    @property
    def is_connected(self) -> bool:
        """Check if the producer is connected to Kafka."""
        return self._connected and self.producer is not None

    async def health_check(self) -> bool:
        """
        Check if the Kafka producer is healthy.

        Returns:
            True if the producer is connected, False otherwise
        """
        # Simple check - just verify producer exists
        # Don't call list_topics as it can block for several seconds
        # which causes health check timeouts
        return self.producer is not None
