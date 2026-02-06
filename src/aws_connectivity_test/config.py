"""
Configuration Management for AWS Connectivity Test Service
==========================================================

This module manages all application configuration using Pydantic Settings.
Configuration is loaded from environment variables, with sensible defaults
for local development.

Environment Variables:
---------------------
All configuration can be set via environment variables. The variable names
match the field names in UPPER_SNAKE_CASE format.

For Kubernetes deployments, these are typically set via:
- ConfigMaps for non-sensitive configuration
- ExternalSecrets for sensitive values (API keys, passwords)
- Helm values for environment-specific configuration

IAM Authentication:
------------------
When deployed to Kubernetes with IRSA (IAM Roles for Service Accounts),
the service uses IAM authentication for:
- MSK (Kafka): SASL_SSL with aws-msk-iam-sasl-signer
- RDS (PostgreSQL): IAM database authentication tokens
- OpenSearch Serverless: SigV4 request signing

For local development, password-based authentication is used instead.
"""

from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    This class uses Pydantic Settings to automatically load configuration
    from environment variables. Fields can have defaults for local development,
    and validators ensure configuration is valid before the service starts.
    """

    # -------------------------------------------------------------------------
    # Settings Configuration
    # -------------------------------------------------------------------------
    # This tells Pydantic Settings how to load environment variables:
    # - env_file: Load from .env file if present (useful for local development)
    # - case_sensitive: Environment variables are case-insensitive
    # -------------------------------------------------------------------------
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # -------------------------------------------------------------------------
    # Kafka / AWS MSK Configuration
    # -------------------------------------------------------------------------
    # These settings control the Kafka consumer connection.
    # For AWS MSK, use SASL_SSL protocol with IAM authentication.
    # For local development, use PLAINTEXT with no authentication.
    # -------------------------------------------------------------------------

    kafka_bootstrap_servers: str = Field(
        default="localhost:9092",
        description="Kafka bootstrap servers (comma-separated list of broker addresses)",
    )

    kafka_topics: str = Field(
        default="test-topic",
        description="Kafka topics to consume from (comma-separated list)",
    )

    kafka_consumer_group: str = Field(
        default="connectivity-test",
        description="Kafka consumer group ID for partition assignment and offset tracking",
    )

    kafka_security_protocol: str = Field(
        default="PLAINTEXT",
        description="Security protocol: PLAINTEXT for local, SASL_SSL for MSK",
    )

    kafka_use_iam_auth: bool = Field(
        default=False,
        description="Enable MSK IAM authentication (requires IRSA in Kubernetes)",
    )

    kafka_auto_offset_reset: str = Field(
        default="earliest",
        description="Where to start consuming: 'earliest' or 'latest'",
    )

    kafka_enable_auto_commit: bool = Field(
        default=False,
        description="Auto-commit offsets (False = manual commit after processing)",
    )

    kafka_session_timeout_ms: int = Field(
        default=45000,
        description="Session timeout for consumer group membership (milliseconds)",
    )

    kafka_max_poll_interval_ms: int = Field(
        default=300000,
        description="Maximum time between polls before consumer is considered dead",
    )

    # -------------------------------------------------------------------------
    # PostgreSQL / AWS RDS Configuration
    # -------------------------------------------------------------------------
    # These settings control the PostgreSQL database connection.
    # For AWS RDS with IAM auth, the password is replaced with an IAM token.
    # IAM tokens are generated using boto3 and have a 15-minute validity.
    # -------------------------------------------------------------------------

    postgres_host: str = Field(
        default="localhost",
        description="PostgreSQL host (RDS endpoint for AWS)",
    )

    postgres_port: int = Field(
        default=5432,
        description="PostgreSQL port (usually 5432)",
    )

    postgres_db: str = Field(
        default="connectivity_test",
        description="PostgreSQL database name",
    )

    postgres_user: str = Field(
        default="postgres",
        description="PostgreSQL username (IAM user for RDS IAM auth)",
    )

    postgres_password: str = Field(
        default="postgres",
        description="PostgreSQL password (only used when IAM auth is disabled)",
    )

    postgresql_use_iam_auth: bool = Field(
        default=False,
        description="Enable RDS IAM authentication (requires IRSA in Kubernetes)",
    )

    postgres_ssl: str = Field(
        default="disable",
        description="SSL mode: 'disable', 'require', 'verify-ca', 'verify-full' (RDS requires at least 'require')",
    )

    postgres_pool_min_size: int = Field(
        default=2,
        description="Minimum number of connections in the pool",
    )

    postgres_pool_max_size: int = Field(
        default=10,
        description="Maximum number of connections in the pool",
    )

    # -------------------------------------------------------------------------
    # OpenSearch Serverless Configuration
    # -------------------------------------------------------------------------
    # These settings control the OpenSearch Serverless connection.
    # OpenSearch Serverless requires IAM authentication via SigV4 signing.
    # The endpoint URL is specific to your OpenSearch Serverless collection.
    # -------------------------------------------------------------------------

    opensearch_endpoint: str = Field(
        default="http://localhost:9200",
        description="OpenSearch endpoint URL (AOSS endpoint for Serverless)",
    )

    opensearch_index: str = Field(
        default="connectivity-test-vectors",
        description="OpenSearch index name for storing vectors",
    )

    opensearch_use_iam_auth: bool = Field(
        default=False,
        description="Enable OpenSearch IAM authentication (SigV4 signing)",
    )

    opensearch_enabled: bool = Field(
        default=True,
        description="Enable OpenSearch integration (disable for local testing)",
    )

    opensearch_vector_dimensions: int = Field(
        default=1024,
        description="Vector dimensions for k-NN index (1024 for Titan, 1536 for text-embedding-3-small)",
    )

    # -------------------------------------------------------------------------
    # Redis / AWS ElastiCache Configuration
    # -------------------------------------------------------------------------
    # These settings control the Redis/ElastiCache connection for status tracking.
    # For AWS ElastiCache with IAM auth, the password is replaced with an IAM token.
    # IAM tokens are generated using botocore RequestSigner with a 15-minute validity.
    # -------------------------------------------------------------------------

    redis_host: str = Field(
        default="localhost",
        description="Redis host (ElastiCache endpoint for AWS)",
    )

    redis_port: int = Field(
        default=6379,
        description="Redis port (usually 6379)",
    )

    redis_use_iam_auth: bool = Field(
        default=False,
        description="Enable ElastiCache IAM authentication (requires IRSA in Kubernetes)",
    )

    redis_enabled: bool = Field(
        default=True,
        description="Enable Redis integration (disable for local testing)",
    )

    redis_cluster_name: str = Field(
        default="",
        description="ElastiCache cluster name for IAM auth (replication group ID)",
    )

    redis_user: str = Field(
        default="default",
        description="Redis username for IAM auth (usually 'default')",
    )

    redis_status_ttl: int = Field(
        default=3600,
        description="TTL for status entries in seconds (default 1 hour)",
    )

    # -------------------------------------------------------------------------
    # OpenAI Configuration
    # -------------------------------------------------------------------------
    # These settings control the OpenAI API client for generating embeddings.
    # The API key should be stored in AWS Secrets Manager for production.
    # -------------------------------------------------------------------------

    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key (from AWS Secrets Manager in production)",
    )

    openai_base_url: Optional[str] = Field(
        default=None,
        description="Custom base URL for OpenAI-compatible API (e.g., Anthropic)",
    )

    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model to use",
    )

    openai_enabled: bool = Field(
        default=True,
        description="Enable OpenAI integration (disable for local testing)",
    )

    # -------------------------------------------------------------------------
    # AWS Configuration
    # -------------------------------------------------------------------------
    # These settings are used for IAM authentication with AWS services.
    # The region must match where your AWS resources are deployed.
    # Credentials are obtained automatically from the IRSA service account.
    # -------------------------------------------------------------------------

    aws_region: str = Field(
        default="eu-west-2",
        description="AWS region for all services (MSK, RDS, OpenSearch)",
    )

    # -------------------------------------------------------------------------
    # Application Configuration
    # -------------------------------------------------------------------------
    # These settings control application behavior and logging.
    # -------------------------------------------------------------------------

    log_level: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR",
    )

    log_format: str = Field(
        default="json",
        description="Log format: 'json' for production, 'console' for development",
    )

    service_name: str = Field(
        default="aws-connectivity-test",
        description="Service name for logging and tracing",
    )

    service_version: str = Field(
        default="0.1.0",
        description="Service version for logging",
    )

    shutdown_timeout: int = Field(
        default=30,
        description="Graceful shutdown timeout in seconds",
    )

    max_concurrent_messages: int = Field(
        default=10,
        description="Maximum number of messages to process concurrently",
    )

    # -------------------------------------------------------------------------
    # Validators
    # -------------------------------------------------------------------------
    # These validators ensure configuration values are valid before the
    # service starts. Invalid configuration causes a clear error message.
    # -------------------------------------------------------------------------

    @field_validator("kafka_topics")
    @classmethod
    def validate_topics(cls, v: str) -> str:
        """
        Validate that at least one Kafka topic is specified.

        Args:
            v: The comma-separated topic string

        Returns:
            The validated topic string

        Raises:
            ValueError: If no valid topics are specified
        """
        topics = [t.strip() for t in v.split(",") if t.strip()]
        if not topics:
            raise ValueError("At least one Kafka topic must be specified")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """
        Validate that log level is a valid Python logging level.

        Args:
            v: The log level string

        Returns:
            The validated log level string (uppercase)

        Raises:
            ValueError: If the log level is not recognized
        """
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {', '.join(valid_levels)}")
        return v.upper()

    # -------------------------------------------------------------------------
    # Computed Properties
    # -------------------------------------------------------------------------
    # These properties provide convenient access to derived configuration.
    # -------------------------------------------------------------------------

    @property
    def kafka_topics_list(self) -> List[str]:
        """
        Get the list of Kafka topics to consume from.

        Returns:
            List of topic names with whitespace trimmed
        """
        return [t.strip() for t in self.kafka_topics.split(",") if t.strip()]

    @property
    def database_url(self) -> str:
        """
        Get the PostgreSQL connection URL.

        Note: This URL uses password auth. For IAM auth, the password
        is replaced with an IAM token at connection time.

        Returns:
            PostgreSQL connection URL string
        """
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


# -----------------------------------------------------------------------------
# Settings Singleton
# -----------------------------------------------------------------------------
# We use a module-level variable to cache the settings instance.
# This ensures settings are loaded once and reused throughout the application.
# -----------------------------------------------------------------------------

_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get the application settings instance.

    This function returns a cached Settings instance. On first call,
    it loads settings from environment variables and .env file.

    Returns:
        The Settings instance with all configuration loaded

    Example:
        settings = get_settings()
        print(f"Connecting to Kafka at {settings.kafka_bootstrap_servers}")
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
