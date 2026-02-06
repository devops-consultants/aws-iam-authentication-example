"""
OpenAI Embeddings Client
========================

This module provides an async client for generating vector embeddings using
the OpenAI API. It handles authentication, model selection, and error handling.

Embedding Generation:
--------------------
The client uses OpenAI's embedding models to convert text into dense vector
representations. These vectors can be used for:
- Semantic search in vector databases
- Document similarity comparison
- Clustering and classification

Supported Models:
----------------
- text-embedding-3-small: 1536 dimensions, good balance of quality and cost
- text-embedding-3-large: 3072 dimensions, highest quality
- text-embedding-ada-002: 1536 dimensions, legacy model

The model is configurable via the OPENAI_EMBEDDING_MODEL environment variable.

API Key Management:
------------------
The OpenAI API key should be stored in AWS Secrets Manager and injected
via Kubernetes ExternalSecret. The key is accessed through the
OPENAI_API_KEY environment variable.

Error Handling:
--------------
The client handles common API errors:
- Rate limiting (429): Logged clearly, not retried automatically
- Timeout: Logged with request details
- Invalid model: Clear error message
- Empty input: Warning logged, skipped

Usage:
------
    from aws_connectivity_test.openai_client import OpenAIClient
    from aws_connectivity_test.config import get_settings

    async def main():
        settings = get_settings()
        client = OpenAIClient(settings)

        embedding = await client.generate_embedding("Hello, World!")
        print(f"Generated embedding with {len(embedding)} dimensions")
"""

import time
from typing import Optional

from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError

from .config import Settings
from .exceptions import OpenAIConnectionError, OpenAIEmbeddingError
from .logging_config import get_logger

# Get a logger for this module
logger = get_logger(__name__)


class OpenAIClient:
    """
    Async OpenAI client for generating embeddings.

    This client wraps the OpenAI SDK to provide:
    - Configuration from application settings
    - Verbose logging for debugging
    - Proper error handling and reporting
    - Latency tracking for performance monitoring

    Attributes:
        settings: Application settings containing OpenAI configuration
        client: AsyncOpenAI client instance (None until initialize())
        _initialized: Whether the client is initialized
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the OpenAI client.

        Args:
            settings: Application settings with OpenAI configuration
        """
        self.settings = settings
        self.client: Optional[AsyncOpenAI] = None
        self._initialized = False

        # Log initialization (mask API key for security)
        logger.info(
            "OpenAI client initialized",
            model=settings.openai_embedding_model,
            api_key_present=settings.openai_api_key is not None,
            api_key_length=len(settings.openai_api_key) if settings.openai_api_key else 0,
            base_url=settings.openai_base_url,
            enabled=settings.openai_enabled,
        )

    async def initialize(self) -> None:
        """
        Initialize the OpenAI client and verify connectivity.

        This method:
        1. Creates the AsyncOpenAI client with the configured API key
        2. Validates the API key by making a test request (optional)

        Raises:
            OpenAIConnectionError: If initialization fails
        """
        if not self.settings.openai_enabled:
            logger.info("OpenAI integration disabled, skipping initialization")
            return

        logger.info("Initializing OpenAI client...")

        try:
            # ---------------------------------------------------------------
            # Validate configuration
            # ---------------------------------------------------------------
            if not self.settings.openai_api_key:
                raise OpenAIConnectionError(
                    "OpenAI API key not configured. "
                    "Set OPENAI_API_KEY environment variable."
                )

            # ---------------------------------------------------------------
            # Create the async client
            # ---------------------------------------------------------------
            # The AsyncOpenAI client handles connection pooling and retries
            # We use it in async context for non-blocking API calls
            # A custom base_url can be provided for OpenAI-compatible APIs
            # (e.g., Anthropic's API with OpenAI compatibility)
            # ---------------------------------------------------------------
            logger.debug(
                "Creating AsyncOpenAI client",
                model=self.settings.openai_embedding_model,
                base_url=self.settings.openai_base_url,
            )

            client_kwargs = {
                "api_key": self.settings.openai_api_key,
            }
            if self.settings.openai_base_url:
                client_kwargs["base_url"] = self.settings.openai_base_url

            self.client = AsyncOpenAI(**client_kwargs)

            self._initialized = True

            logger.info(
                "OpenAI client initialized successfully",
                model=self.settings.openai_embedding_model,
            )

        except OpenAIConnectionError:
            raise
        except Exception as e:
            logger.error(
                "Failed to initialize OpenAI client",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise OpenAIConnectionError(f"Failed to initialize OpenAI client: {e}")

    async def generate_embedding(
        self,
        text: str,
    ) -> list[float]:
        """
        Generate an embedding vector for the given text.

        This method calls the OpenAI embeddings API to convert text into
        a dense vector representation. The vector can be used for semantic
        search, similarity comparison, etc.

        Args:
            text: The text to generate an embedding for

        Returns:
            List of floats representing the embedding vector

        Raises:
            OpenAIEmbeddingError: If embedding generation fails
            OpenAIConnectionError: If client is not initialized
        """
        if not self.settings.openai_enabled:
            logger.debug("OpenAI disabled, returning empty embedding")
            return []

        if not self.client:
            raise OpenAIConnectionError("OpenAI client not initialized")

        # ---------------------------------------------------------------
        # Validate input
        # ---------------------------------------------------------------
        # Skip empty or whitespace-only input to avoid API errors
        # ---------------------------------------------------------------
        if not text or not text.strip():
            logger.warning(
                "Empty or whitespace-only text provided, skipping embedding",
                text_length=len(text) if text else 0,
            )
            return []

        start_time = time.time()

        logger.debug(
            "Generating embedding",
            model=self.settings.openai_embedding_model,
            text_length=len(text),
        )

        try:
            # ---------------------------------------------------------------
            # Call the OpenAI API
            # ---------------------------------------------------------------
            # The embeddings.create() method sends the text to OpenAI and
            # returns the embedding vector. We use the configured model.
            # ---------------------------------------------------------------
            response = await self.client.embeddings.create(
                model=self.settings.openai_embedding_model,
                input=text,
            )

            # Extract the embedding from the response
            # The response contains a list of embeddings (one per input)
            embedding = response.data[0].embedding

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Embedding generated successfully",
                model=self.settings.openai_embedding_model,
                input_length=len(text),
                dimensions=len(embedding),
                duration_ms=duration_ms,
                usage_tokens=response.usage.total_tokens if response.usage else None,
            )

            return embedding

        except RateLimitError as e:
            # ---------------------------------------------------------------
            # Handle rate limiting (429 errors)
            # ---------------------------------------------------------------
            # OpenAI has rate limits on API calls. When exceeded, we log
            # the error but don't retry automatically. The caller should
            # implement backoff if needed.
            # ---------------------------------------------------------------
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "OpenAI rate limit exceeded",
                error=str(e),
                model=self.settings.openai_embedding_model,
                input_length=len(text),
                duration_ms=duration_ms,
            )
            raise OpenAIEmbeddingError(
                f"OpenAI rate limit exceeded: {e}",
                details={
                    "model": self.settings.openai_embedding_model,
                    "input_length": len(text),
                },
            )

        except APITimeoutError as e:
            # ---------------------------------------------------------------
            # Handle timeout errors
            # ---------------------------------------------------------------
            # The API request took too long. This could be due to network
            # issues or OpenAI service problems.
            # ---------------------------------------------------------------
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "OpenAI API timeout",
                error=str(e),
                model=self.settings.openai_embedding_model,
                input_length=len(text),
                duration_ms=duration_ms,
            )
            raise OpenAIEmbeddingError(
                f"OpenAI API timeout: {e}",
                details={
                    "model": self.settings.openai_embedding_model,
                    "input_length": len(text),
                    "duration_ms": duration_ms,
                },
            )

        except APIError as e:
            # ---------------------------------------------------------------
            # Handle other API errors
            # ---------------------------------------------------------------
            # This includes invalid model, authentication errors, etc.
            # ---------------------------------------------------------------
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "OpenAI API error",
                error=str(e),
                error_code=getattr(e, "code", None),
                model=self.settings.openai_embedding_model,
                input_length=len(text),
                duration_ms=duration_ms,
            )
            raise OpenAIEmbeddingError(
                f"OpenAI API error: {e}",
                details={
                    "model": self.settings.openai_embedding_model,
                    "input_length": len(text),
                    "error_code": getattr(e, "code", None),
                },
            )

        except Exception as e:
            # ---------------------------------------------------------------
            # Handle unexpected errors
            # ---------------------------------------------------------------
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Unexpected error generating embedding",
                error=str(e),
                error_type=type(e).__name__,
                model=self.settings.openai_embedding_model,
                input_length=len(text),
                duration_ms=duration_ms,
            )
            raise OpenAIEmbeddingError(
                f"Unexpected error generating embedding: {e}",
                details={
                    "model": self.settings.openai_embedding_model,
                    "input_length": len(text),
                },
            )

    async def close(self) -> None:
        """
        Close the OpenAI client.

        The AsyncOpenAI client uses httpx which manages its own connection
        pool. We just clear the reference here.
        """
        if self.client:
            logger.info("Closing OpenAI client...")
            # AsyncOpenAI client manages its own cleanup
            await self.client.close()
            self.client = None
            self._initialized = False
            logger.info("OpenAI client closed")

    @property
    def is_initialized(self) -> bool:
        """Check if the client is initialized."""
        return self._initialized and self.client is not None

    async def health_check(self) -> bool:
        """
        Check if the OpenAI client is healthy.

        Returns:
            True if the client is initialized and API key is valid,
            False otherwise
        """
        if not self.settings.openai_enabled:
            return True  # Disabled is considered "healthy"

        if not self.client:
            return False

        # We don't make a test API call to avoid unnecessary costs
        # Just check that the client is initialized with a valid key
        return self.settings.openai_api_key is not None

    def get_model_info(self) -> dict:
        """
        Get information about the configured embedding model.

        Returns:
            Dictionary with model information
        """
        # Known model dimensions
        model_dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }

        model = self.settings.openai_embedding_model
        return {
            "model": model,
            "dimensions": model_dimensions.get(model, "unknown"),
            "enabled": self.settings.openai_enabled,
        }
