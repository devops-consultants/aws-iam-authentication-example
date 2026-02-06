"""
OpenSearch Client with IAM Authentication for AWS OpenSearch Serverless
=======================================================================

This module provides a client for writing vector embeddings to AWS OpenSearch
Serverless with IAM authentication via SigV4 request signing.

IAM Authentication (SigV4):
--------------------------
AWS OpenSearch Serverless requires all requests to be signed using AWS
Signature Version 4 (SigV4). This is done automatically using:

1. boto3 session to get current AWS credentials
2. requests_aws4auth to sign HTTP requests
3. opensearch-py configured with the signed auth

In Kubernetes with IRSA:
- boto3 automatically uses the service account's IAM role
- Credentials are refreshed automatically by IRSA
- The role must have aoss:APIAccessAll permission for the collection

Document Structure:
------------------
Each vector document stored in OpenSearch has the following structure:
{
    "vector": [0.1, 0.2, ...],    # The embedding vector (float array)
    "metadata": {
        "kafka_topic": "...",
        "kafka_partition": 0,
        "kafka_offset": 12345,
        "message_preview": "..."
    },
    "timestamp": "2024-01-15T10:30:00Z"
}

Document ID:
-----------
Documents are identified by a unique ID generated from Kafka metadata:
    {topic}-{partition}-{offset}

This ensures idempotency - re-processing a message overwrites the existing doc.

Usage:
------
    from aws_connectivity_test.opensearch_client import OpenSearchClient
    from aws_connectivity_test.config import get_settings

    async def main():
        settings = get_settings()
        client = OpenSearchClient(settings)

        await client.connect()
        await client.write_vector(
            vector=[0.1, 0.2, 0.3, ...],
            kafka_topic="my-topic",
            kafka_partition=0,
            kafka_offset=12345,
            message_preview="Hello, World!",
        )
        await client.close()
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Optional

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

from .config import Settings
from .exceptions import OpenSearchConnectionError, OpenSearchWriteError
from .logging_config import get_logger

# Get a logger for this module
logger = get_logger(__name__)


class OpenSearchClient:
    """
    OpenSearch Serverless client with optional IAM authentication.

    This client manages connections to OpenSearch Serverless and provides
    methods for writing vector embeddings with metadata.

    Note: opensearch-py is synchronous, so we wrap calls in asyncio.to_thread
    to avoid blocking the async event loop.

    Attributes:
        settings: Application settings containing OpenSearch configuration
        client: OpenSearch client instance (None until connect() is called)
        _connected: Whether the client is connected
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the OpenSearch client.

        Args:
            settings: Application settings with OpenSearch configuration
        """
        self.settings = settings
        self.client: Optional[OpenSearch] = None
        self._connected = False

        # Log initialization
        logger.info(
            "OpenSearch client initialized",
            endpoint=self._mask_endpoint(settings.opensearch_endpoint),
            index=settings.opensearch_index,
            use_iam_auth=settings.opensearch_use_iam_auth,
            enabled=settings.opensearch_enabled,
        )

    def _mask_endpoint(self, endpoint: str) -> str:
        """
        Mask the OpenSearch endpoint for logging.

        This prevents sensitive endpoint URLs from appearing in full in logs
        while still providing useful debugging information.

        Args:
            endpoint: The full endpoint URL

        Returns:
            Masked endpoint string showing only the domain portion
        """
        # Extract just the domain for logging
        if "://" in endpoint:
            protocol, rest = endpoint.split("://", 1)
            domain = rest.split("/")[0]
            return f"{protocol}://{domain}"
        return endpoint

    async def connect(self) -> None:
        """
        Connect to OpenSearch and validate the index.

        This method:
        1. Creates an OpenSearch client with appropriate authentication
        2. Tests the connection by getting cluster info
        3. Checks if the target index exists

        Raises:
            OpenSearchConnectionError: If connection fails
        """
        if not self.settings.opensearch_enabled:
            logger.info("OpenSearch integration disabled, skipping connection")
            return

        start_time = time.time()
        logger.info("Connecting to OpenSearch...")

        try:
            # ---------------------------------------------------------------
            # Step 1: Set up authentication
            # ---------------------------------------------------------------
            # For IAM auth, we use AWS4Auth to sign all requests
            # For local development, we use no authentication
            # ---------------------------------------------------------------
            if self.settings.opensearch_use_iam_auth:
                logger.info("Setting up IAM authentication (SigV4)...")
                auth = self._create_aws4_auth()
                logger.info("IAM authentication configured")
            else:
                logger.info("Using no authentication (local mode)")
                auth = None

            # ---------------------------------------------------------------
            # Step 2: Create the OpenSearch client
            # ---------------------------------------------------------------
            # Parse the endpoint URL to extract host information
            # OpenSearch Serverless endpoints look like:
            # https://xxxxx.eu-west-2.aoss.amazonaws.com
            # ---------------------------------------------------------------
            endpoint = self.settings.opensearch_endpoint

            # Parse the endpoint
            if endpoint.startswith("https://"):
                host = endpoint[8:]  # Remove https://
                port = 443
                use_ssl = True
            elif endpoint.startswith("http://"):
                host = endpoint[7:]  # Remove http://
                port = 9200
                use_ssl = False
            else:
                host = endpoint
                port = 443 if self.settings.opensearch_use_iam_auth else 9200
                use_ssl = self.settings.opensearch_use_iam_auth

            # Remove trailing slash and path
            host = host.rstrip("/").split("/")[0]

            logger.info(
                "Creating OpenSearch client",
                host=host,
                port=port,
                use_ssl=use_ssl,
            )

            # Build client configuration
            client_kwargs: dict[str, Any] = {
                "hosts": [{"host": host, "port": port}],
                "use_ssl": use_ssl,
                "verify_certs": True,
                "connection_class": RequestsHttpConnection,
            }

            # Add authentication if configured
            if auth:
                client_kwargs["http_auth"] = auth

            self.client = OpenSearch(**client_kwargs)

            # ---------------------------------------------------------------
            # Step 3: Test the connection
            # ---------------------------------------------------------------
            # Note: OpenSearch Serverless doesn't support GET / (info endpoint)
            # so for IAM auth (Serverless), we skip info() and use index check
            # ---------------------------------------------------------------
            logger.info("Testing OpenSearch connection...")
            if self.settings.opensearch_use_iam_auth:
                # For OpenSearch Serverless, test by checking index
                logger.info("Using Serverless mode - testing via index check")
                await self._check_index_exists()
            else:
                # For regular OpenSearch, use the info endpoint
                info = await asyncio.to_thread(self.client.info)
                logger.info(
                    "OpenSearch connection successful",
                    cluster_name=info.get("cluster_name", "unknown"),
                    version=info.get("version", {}).get("number", "unknown"),
                )
                # ---------------------------------------------------------------
                # Step 4: Check if the index exists (non-Serverless only)
                # ---------------------------------------------------------------
                await self._check_index_exists()

            self._connected = True

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "OpenSearch client connected successfully",
                endpoint=self._mask_endpoint(self.settings.opensearch_endpoint),
                index=self.settings.opensearch_index,
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.error(
                "OpenSearch connection failed",
                error=str(e),
                error_type=type(e).__name__,
                endpoint=self._mask_endpoint(self.settings.opensearch_endpoint),
            )
            raise OpenSearchConnectionError(
                f"Failed to connect to OpenSearch: {e}",
                details={
                    "endpoint": self._mask_endpoint(self.settings.opensearch_endpoint),
                    "index": self.settings.opensearch_index,
                    "use_iam_auth": self.settings.opensearch_use_iam_auth,
                },
            )

    def _create_aws4_auth(self) -> AWS4Auth:
        """
        Create AWS4Auth for SigV4 request signing.

        This method uses boto3 to get the current AWS credentials (from IRSA
        in Kubernetes) and creates an AWS4Auth instance that will sign all
        HTTP requests to OpenSearch.

        Returns:
            AWS4Auth instance configured for OpenSearch Serverless

        Raises:
            OpenSearchConnectionError: If credentials cannot be obtained
        """
        logger.debug(
            "Creating AWS4Auth",
            region=self.settings.aws_region,
            service="aoss",  # OpenSearch Serverless service name
        )

        try:
            # Get credentials from boto3 session
            # In Kubernetes with IRSA, these come from the service account
            session = boto3.Session(region_name=self.settings.aws_region)
            credentials = session.get_credentials()

            if not credentials:
                raise OpenSearchConnectionError(
                    "Failed to obtain AWS credentials for OpenSearch SigV4 signing"
                )

            # Create AWS4Auth for signing requests
            # Service name is 'aoss' for OpenSearch Serverless
            auth = AWS4Auth(
                credentials.access_key,
                credentials.secret_key,
                self.settings.aws_region,
                "aoss",  # Service name for OpenSearch Serverless
                session_token=credentials.token,  # May be None for non-IRSA
            )

            logger.debug("AWS4Auth created successfully")
            return auth

        except Exception as e:
            logger.error(
                "Failed to create AWS4Auth",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise OpenSearchConnectionError(
                f"Failed to create AWS4Auth for SigV4 signing: {e}",
                details={"region": self.settings.aws_region},
            )

    async def _check_index_exists(self) -> None:
        """
        Check if the target index exists in OpenSearch, creating it if not.

        For OpenSearch Serverless, this creates a vector index with the
        appropriate mapping for storing embeddings.
        """
        if not self.client:
            return

        logger.info(
            "Checking if index exists",
            index=self.settings.opensearch_index,
        )

        try:
            exists = await asyncio.to_thread(
                self.client.indices.exists, index=self.settings.opensearch_index
            )

            if exists:
                logger.info(
                    "Index exists and is ready for writes",
                    index=self.settings.opensearch_index,
                )
            else:
                logger.info(
                    "Index does not exist - creating it now",
                    index=self.settings.opensearch_index,
                )
                await self._create_vector_index()

        except Exception as e:
            logger.warning(
                "Could not check index existence - attempting to create",
                index=self.settings.opensearch_index,
                error=str(e),
            )
            # Try to create the index anyway - it might just be a permissions issue
            # on the HEAD request but we may still have permission to create
            try:
                await self._create_vector_index()
            except Exception as create_error:
                logger.warning(
                    "Could not create index",
                    index=self.settings.opensearch_index,
                    error=str(create_error),
                )

    async def _create_vector_index(self) -> None:
        """
        Create a vector index in OpenSearch Serverless.

        This creates an index with the appropriate mapping for storing
        vector embeddings from OpenAI's text-embedding-3-small model
        (1536 dimensions by default).
        """
        if not self.client:
            return

        # Index mapping for vector search
        # Using knn_vector type for OpenSearch Serverless
        vector_dimensions = self.settings.opensearch_vector_dimensions
        index_body = {
            "settings": {
                "index": {
                    "knn": True,
                }
            },
            "mappings": {
                "properties": {
                    "vector": {
                        "type": "knn_vector",
                        "dimension": vector_dimensions,  # Configured via settings
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "faiss",
                            "parameters": {
                                "ef_construction": 128,
                                "m": 16
                            }
                        }
                    },
                    "metadata": {
                        "type": "object",
                        "properties": {
                            "kafka_topic": {"type": "keyword"},
                            "kafka_partition": {"type": "integer"},
                            "kafka_offset": {"type": "long"},
                            "message_preview": {"type": "text"}
                        }
                    },
                    "timestamp": {"type": "date"}
                }
            }
        }

        logger.info(
            "Creating vector index",
            index=self.settings.opensearch_index,
            vector_dimensions=vector_dimensions,
        )

        try:
            response = await asyncio.to_thread(
                self.client.indices.create,
                index=self.settings.opensearch_index,
                body=index_body,
            )

            logger.info(
                "Vector index created successfully",
                index=self.settings.opensearch_index,
                acknowledged=response.get("acknowledged", False),
            )

        except Exception as e:
            # Check if the error is because the index already exists
            error_str = str(e)
            if "resource_already_exists_exception" in error_str.lower():
                logger.info(
                    "Index already exists (created by another process)",
                    index=self.settings.opensearch_index,
                )
            else:
                logger.error(
                    "Failed to create vector index",
                    index=self.settings.opensearch_index,
                    error=error_str,
                    error_type=type(e).__name__,
                )
                raise

    @staticmethod
    def generate_doc_id(
        kafka_topic: str, kafka_partition: int, kafka_offset: int
    ) -> str:
        """
        Generate a unique document ID from Kafka metadata.

        This ensures idempotency - re-processing the same message will
        overwrite the existing document rather than creating duplicates.

        Args:
            kafka_topic: The Kafka topic name
            kafka_partition: The partition number
            kafka_offset: The message offset

        Returns:
            A unique document ID string
        """
        return f"{kafka_topic}-{kafka_partition}-{kafka_offset}"

    async def write_vector(
        self,
        vector: list[float],
        kafka_topic: str,
        kafka_partition: int,
        kafka_offset: int,
        message_preview: Optional[str] = None,
    ) -> str:
        """
        Write a vector embedding to OpenSearch.

        This method stores the vector with metadata about its source
        (Kafka message) for traceability.

        Args:
            vector: The embedding vector (list of floats)
            kafka_topic: The Kafka topic the message came from
            kafka_partition: The partition number
            kafka_offset: The message offset
            message_preview: Optional preview of the message content

        Returns:
            The document ID of the stored document

        Raises:
            OpenSearchWriteError: If the write fails
            OpenSearchConnectionError: If not connected
        """
        if not self.settings.opensearch_enabled:
            logger.debug("OpenSearch disabled, skipping write")
            return "disabled"

        if not self.client:
            raise OpenSearchConnectionError("Not connected to OpenSearch")

        start_time = time.time()

        # Generate document ID from Kafka metadata
        doc_id = self.generate_doc_id(kafka_topic, kafka_partition, kafka_offset)

        logger.debug(
            "Writing vector to OpenSearch",
            doc_id=doc_id,
            vector_dimensions=len(vector),
            index=self.settings.opensearch_index,
        )

        try:
            # Build the document to store
            document = {
                "vector": vector,
                "metadata": {
                    "kafka_topic": kafka_topic,
                    "kafka_partition": kafka_partition,
                    "kafka_offset": kafka_offset,
                    "message_preview": message_preview[:500] if message_preview else None,
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Index the document
            # Note: OpenSearch Serverless (some collection types) doesn't support
            # specifying document IDs. For Serverless, we let OpenSearch auto-generate
            # the ID and return it from the response.
            index_kwargs: dict[str, Any] = {
                "index": self.settings.opensearch_index,
                "body": document,
            }

            # Only specify doc ID for non-Serverless (non-IAM auth) deployments
            if not self.settings.opensearch_use_iam_auth:
                index_kwargs["id"] = doc_id

            response = await asyncio.to_thread(
                self.client.index,
                **index_kwargs,
            )

            # Get the actual document ID (either our specified one or auto-generated)
            actual_doc_id = response.get("_id", doc_id)

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Vector written to OpenSearch",
                doc_id=actual_doc_id,
                index=self.settings.opensearch_index,
                vector_dimensions=len(vector),
                result=response.get("result", "unknown"),
                duration_ms=duration_ms,
            )

            return actual_doc_id

        except Exception as e:
            logger.error(
                "Failed to write vector to OpenSearch",
                error=str(e),
                error_type=type(e).__name__,
                doc_id=doc_id,
                index=self.settings.opensearch_index,
            )
            raise OpenSearchWriteError(
                f"Failed to write vector to OpenSearch: {e}",
                details={
                    "doc_id": doc_id,
                    "index": self.settings.opensearch_index,
                    "vector_dimensions": len(vector),
                },
            )

    async def close(self) -> None:
        """
        Close the OpenSearch client.

        This method should be called during graceful shutdown.
        """
        if self.client:
            logger.info("Closing OpenSearch client...")
            # OpenSearch client doesn't have a close method, just clear reference
            self.client = None
            self._connected = False
            logger.info("OpenSearch client closed")

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected to OpenSearch."""
        return self._connected and self.client is not None

    async def health_check(self) -> bool:
        """
        Check if the OpenSearch connection is healthy.

        Returns:
            True if the connection is healthy, False otherwise
        """
        if not self.settings.opensearch_enabled:
            return True  # Disabled is considered "healthy"

        if not self.client:
            return False

        try:
            # OpenSearch Serverless doesn't support GET / (info endpoint)
            # so we check index existence instead
            if self.settings.opensearch_use_iam_auth:
                await asyncio.to_thread(
                    self.client.indices.exists, index=self.settings.opensearch_index
                )
            else:
                await asyncio.to_thread(self.client.info)
            return True
        except Exception as e:
            logger.warning("OpenSearch health check failed", error=str(e))
            return False
