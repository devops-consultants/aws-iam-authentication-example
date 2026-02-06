"""
Pytest Configuration and Fixtures for AWS Connectivity Test Service
====================================================================

This module provides shared fixtures for testing the connectivity test
service. It includes mocked AWS clients and configuration.

Fixtures:
--------
- settings: Application settings with test defaults
- mock_postgres: Mocked PostgreSQL client
- mock_opensearch: Mocked OpenSearch client
- mock_openai: Mocked OpenAI client
- mock_kafka: Mocked Kafka consumer
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def test_settings():
    """
    Create test settings with default values.

    Returns a Settings instance configured for local testing
    with all IAM authentication disabled.
    """
    from aws_connectivity_test.config import Settings

    return Settings(
        # Kafka settings
        kafka_bootstrap_servers="localhost:9092",
        kafka_topics="test-topic",
        kafka_consumer_group="test-consumer-group",
        kafka_security_protocol="PLAINTEXT",
        kafka_use_iam_auth=False,

        # PostgreSQL settings
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="test_db",
        postgres_user="test_user",
        postgres_password="test_password",
        postgresql_use_iam_auth=False,

        # OpenSearch settings
        opensearch_endpoint="http://localhost:9200",
        opensearch_index="test-index",
        opensearch_use_iam_auth=False,
        opensearch_enabled=True,

        # OpenAI settings
        openai_api_key="test-api-key",
        openai_embedding_model="text-embedding-3-small",
        openai_enabled=True,

        # AWS settings
        aws_region="eu-west-2",

        # Application settings
        log_level="DEBUG",
        log_format="console",
        service_name="test-service",
        service_version="0.0.1",
        shutdown_timeout=5,
        max_concurrent_messages=2,
    )


@pytest.fixture
def mock_asyncpg_pool():
    """
    Create a mocked asyncpg connection pool.

    Returns a MagicMock that simulates asyncpg pool behavior.
    """
    pool = AsyncMock()

    # Mock acquire context manager
    connection = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = connection

    # Mock connection methods
    connection.fetchval.return_value = True
    connection.fetchrow.return_value = {"id": 1, "timestamp": "2024-01-15T10:00:00Z"}
    connection.execute.return_value = None

    # Mock transaction context manager
    connection.transaction.return_value.__aenter__.return_value = None
    connection.transaction.return_value.__aexit__.return_value = None

    return pool


@pytest.fixture
def mock_opensearch_client():
    """
    Create a mocked OpenSearch client.

    Returns a MagicMock that simulates opensearch-py behavior.
    """
    client = MagicMock()

    # Mock info method
    client.info.return_value = {
        "cluster_name": "test-cluster",
        "version": {"number": "2.11.0"},
    }

    # Mock indices.exists
    client.indices.exists.return_value = True

    # Mock index method
    client.index.return_value = {"result": "created", "_id": "test-doc-id"}

    return client


@pytest.fixture
def mock_openai_client():
    """
    Create a mocked OpenAI async client.

    Returns an AsyncMock that simulates AsyncOpenAI behavior.
    """
    client = AsyncMock()

    # Create mock embedding response
    mock_embedding = MagicMock()
    mock_embedding.embedding = [0.1] * 1536  # Standard embedding dimensions

    mock_response = MagicMock()
    mock_response.data = [mock_embedding]
    mock_response.usage = MagicMock(total_tokens=100)

    # Mock embeddings.create
    client.embeddings.create.return_value = mock_response

    return client


@pytest.fixture
def mock_kafka_consumer():
    """
    Create a mocked aiokafka consumer.

    Returns an AsyncMock that simulates AIOKafkaConsumer behavior.
    """
    consumer = AsyncMock()

    # Mock start/stop
    consumer.start.return_value = None
    consumer.stop.return_value = None

    # Mock assignment
    consumer.assignment.return_value = []

    # Mock getmany (no messages by default)
    consumer.getmany.return_value = {}

    # Mock commit
    consumer.commit.return_value = None

    return consumer


@pytest.fixture
def sample_kafka_message():
    """
    Create a sample Kafka message for testing.

    Returns a MagicMock that simulates an aiokafka message.
    """
    message = MagicMock()
    message.topic = "test-topic"
    message.partition = 0
    message.offset = 12345
    message.key = b"test-key"
    message.value = b"Test message content for embedding"
    message.timestamp = 1705312800000  # 2024-01-15T10:00:00Z

    return message


@pytest.fixture
def mock_boto3_session():
    """
    Create a mocked boto3 session for IAM authentication testing.

    Returns patches for boto3 client and session.
    """
    with patch("boto3.Session") as mock_session, \
         patch("boto3.client") as mock_client:

        # Mock credentials
        mock_credentials = MagicMock()
        mock_credentials.access_key = "test-access-key"
        mock_credentials.secret_key = "test-secret-key"
        mock_credentials.token = "test-session-token"

        mock_session.return_value.get_credentials.return_value = mock_credentials

        # Mock RDS client for IAM token generation
        mock_rds = MagicMock()
        mock_rds.generate_db_auth_token.return_value = "test-iam-token"
        mock_client.return_value = mock_rds

        yield {
            "session": mock_session,
            "client": mock_client,
            "credentials": mock_credentials,
        }
