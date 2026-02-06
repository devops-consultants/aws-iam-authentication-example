"""
Tests for Configuration Management
==================================

These tests verify that the configuration module correctly:
- Loads settings from environment variables
- Validates configuration values
- Provides computed properties
"""

import os
import pytest
from pydantic import ValidationError


class TestSettings:
    """Tests for the Settings class."""

    def test_default_settings(self, test_settings):
        """Test that settings are created with expected defaults."""
        assert test_settings.kafka_bootstrap_servers == "localhost:9092"
        assert test_settings.kafka_topics == "test-topic"
        assert test_settings.postgres_host == "localhost"
        assert test_settings.log_level == "DEBUG"

    def test_kafka_topics_list_property(self, test_settings):
        """Test that kafka_topics_list correctly parses comma-separated topics."""
        # Single topic
        assert test_settings.kafka_topics_list == ["test-topic"]

        # Multiple topics
        test_settings.kafka_topics = "topic1, topic2, topic3"
        assert test_settings.kafka_topics_list == ["topic1", "topic2", "topic3"]

        # Topics with extra whitespace
        test_settings.kafka_topics = "  topic1  ,  topic2  "
        assert test_settings.kafka_topics_list == ["topic1", "topic2"]

    def test_database_url_property(self, test_settings):
        """Test that database_url is correctly constructed."""
        expected = "postgresql://test_user:test_password@localhost:5432/test_db"
        assert test_settings.database_url == expected

    def test_kafka_topics_validation_empty(self):
        """Test that empty Kafka topics raise validation error."""
        from aws_connectivity_test.config import Settings

        with pytest.raises(ValidationError) as exc_info:
            Settings(kafka_topics="   ")

        errors = exc_info.value.errors()
        assert any("kafka_topics" in str(e) for e in errors)

    def test_log_level_validation(self):
        """Test that invalid log levels raise validation error."""
        from aws_connectivity_test.config import Settings

        with pytest.raises(ValidationError) as exc_info:
            Settings(log_level="INVALID")

        errors = exc_info.value.errors()
        assert any("log_level" in str(e) or "Log level" in str(e.get("msg", "")) for e in errors)

    def test_log_level_case_insensitive(self):
        """Test that log level validation is case-insensitive."""
        from aws_connectivity_test.config import Settings

        settings = Settings(log_level="debug")
        assert settings.log_level == "DEBUG"

        settings = Settings(log_level="INFO")
        assert settings.log_level == "INFO"

    def test_get_settings_singleton(self, monkeypatch):
        """Test that get_settings returns the same instance."""
        # Reset the global settings
        import aws_connectivity_test.config as config_module
        config_module._settings = None

        # Set required env vars
        monkeypatch.setenv("KAFKA_TOPICS", "test-topic")

        from aws_connectivity_test.config import get_settings

        settings1 = get_settings()
        settings2 = get_settings()

        # Should be the same instance
        assert settings1 is settings2

        # Clean up
        config_module._settings = None


class TestSettingsFromEnvironment:
    """Tests for loading settings from environment variables."""

    def test_load_from_environment(self, monkeypatch):
        """Test that settings are loaded from environment variables."""
        # Reset the global settings
        import aws_connectivity_test.config as config_module
        config_module._settings = None

        # Set environment variables
        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.example.com:9092")
        monkeypatch.setenv("KAFKA_TOPICS", "my-topic")
        monkeypatch.setenv("POSTGRES_HOST", "db.example.com")
        monkeypatch.setenv("LOG_LEVEL", "WARNING")

        from aws_connectivity_test.config import Settings

        settings = Settings()

        assert settings.kafka_bootstrap_servers == "kafka.example.com:9092"
        assert settings.kafka_topics == "my-topic"
        assert settings.postgres_host == "db.example.com"
        assert settings.log_level == "WARNING"

        # Clean up
        config_module._settings = None

    def test_boolean_environment_variables(self, monkeypatch):
        """Test that boolean settings are correctly parsed from strings."""
        import aws_connectivity_test.config as config_module
        config_module._settings = None

        monkeypatch.setenv("KAFKA_TOPICS", "test-topic")
        monkeypatch.setenv("KAFKA_USE_IAM_AUTH", "true")
        monkeypatch.setenv("POSTGRESQL_USE_IAM_AUTH", "True")
        monkeypatch.setenv("OPENSEARCH_ENABLED", "false")

        from aws_connectivity_test.config import Settings

        settings = Settings()

        assert settings.kafka_use_iam_auth is True
        assert settings.postgresql_use_iam_auth is True
        assert settings.opensearch_enabled is False

        # Clean up
        config_module._settings = None


class TestSettingsValidation:
    """Tests for settings validation."""

    def test_required_fields_have_defaults(self):
        """Test that all required fields have sensible defaults."""
        from aws_connectivity_test.config import Settings

        # Should not raise - all fields have defaults except validation
        settings = Settings(kafka_topics="test")

        # Check key fields have non-empty defaults
        assert settings.kafka_bootstrap_servers
        assert settings.kafka_consumer_group
        assert settings.postgres_host
        assert settings.postgres_db

    def test_port_validation(self):
        """Test that port numbers are valid integers."""
        from aws_connectivity_test.config import Settings

        settings = Settings(
            kafka_topics="test",
            postgres_port=5432,
        )
        assert settings.postgres_port == 5432

    def test_optional_openai_key(self):
        """Test that OpenAI API key is optional."""
        from aws_connectivity_test.config import Settings

        settings = Settings(
            kafka_topics="test",
            openai_api_key=None,
        )
        assert settings.openai_api_key is None

        settings = Settings(
            kafka_topics="test",
            openai_api_key="sk-test123",
        )
        assert settings.openai_api_key == "sk-test123"
