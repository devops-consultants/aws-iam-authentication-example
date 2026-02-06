## 1. Project Structure Setup

- [x] 1.1 Create aws-connectivity-test/ directory with Python package structure (src/, tests/, scripts/)
- [x] 1.2 Create pyproject.toml with project metadata and dependencies
- [x] 1.3 Create requirements.txt with all dependencies (FastAPI, aiokafka, aws-msk-iam-sasl-signer-python, openai, opensearchpy, asyncpg, boto3, structlog)
- [x] 1.4 Create Dockerfile based on data-ingest/Dockerfile pattern with Python 3.11
- [x] 1.5 Create docker-compose.yml for local development (Kafka, Zookeeper, PostgreSQL)
- [x] 1.6 Create .env.example with all required environment variables
- [x] 1.7 Create scripts/local-dev.sh helper script for development commands

## 2. Core Application - Configuration and Logging

- [x] 2.1 Create src/aws_connectivity_test/__init__.py package initialization
- [x] 2.2 Create src/aws_connectivity_test/config.py with pydantic Settings for all environment variables
- [x] 2.3 Create src/aws_connectivity_test/logging_config.py with structlog setup for JSON logging
- [x] 2.4 Create src/aws_connectivity_test/exceptions.py with custom exception classes

## 3. PostgreSQL Client with IAM Authentication

- [x] 3.1 Create src/aws_connectivity_test/postgres_client.py with asyncpg connection setup
- [x] 3.2 Implement IAM token generation using boto3 RDS generate_db_auth_token
- [x] 3.3 Implement connection pool management with token refresh logic
- [x] 3.4 Implement demo_log table creation with full schema (id, timestamp, kafka_topic, kafka_partition, kafka_offset, message_content, embedding_model, embedding_dimensions, opensearch_index, opensearch_doc_id, log_level)
- [x] 3.5 Implement async insert_log_entry method with transaction management
- [x] 3.6 Add verbose logging for connection initialization, table creation, and all operations
- [x] 3.7 Add generous code comments explaining IAM auth flow

## 4. OpenSearch Client with IAM Authentication

- [x] 4.1 Create src/aws_connectivity_test/opensearch_client.py with opensearchpy setup
- [x] 4.2 Implement AWS SigV4 request signing using boto3 credentials
- [x] 4.3 Implement index existence validation on startup
- [x] 4.4 Implement async write_vector method for storing embeddings with metadata
- [x] 4.5 Implement document ID generation from Kafka metadata (topic-partition-offset)
- [x] 4.6 Add verbose logging for connection initialization, index validation, and write operations
- [x] 4.7 Add generous code comments explaining IAM auth and vector storage

## 5. Kafka Consumer with MSK IAM Authentication

- [x] 5.1 Create src/aws_connectivity_test/kafka_consumer.py adapted from data-ingest pattern
- [x] 5.2 Implement MSK IAM authentication callback using aws-msk-iam-sasl-signer-python
- [x] 5.3 Configure aiokafka.AIOKafkaConsumer with SASL_SSL and IAM auth
- [x] 5.4 Implement consumer group management and topic subscription from config
- [x] 5.5 Implement async message consumption loop with offset management
- [x] 5.6 Implement graceful shutdown handler for SIGTERM with offset commit
- [x] 5.7 Add verbose logging for connection, authentication, partition assignment, and consumption
- [x] 5.8 Add generous code comments explaining MSK IAM auth flow

## 6. OpenAI Embeddings Client

- [x] 6.1 Create src/aws_connectivity_test/openai_client.py with AsyncOpenAI setup
- [x] 6.2 Implement async generate_embedding method with configured model
- [x] 6.3 Implement error handling for rate limits and timeouts
- [x] 6.4 Add verbose logging for client initialization and all API calls with latency tracking
- [x] 6.5 Add generous code comments explaining embedding generation

## 7. Service Orchestrator

- [x] 7.1 Create src/aws_connectivity_test/orchestrator.py for pipeline coordination
- [x] 7.2 Implement startup sequence: PostgreSQL → OpenSearch → Kafka → OpenAI initialization
- [x] 7.3 Implement message processing pipeline: consume → embed → write OpenSearch → log PostgreSQL
- [x] 7.4 Implement concurrent message processing with configurable limit
- [x] 7.5 Implement error handling with context preservation for each pipeline step
- [x] 7.6 Add processing metrics logging (latencies for each operation)
- [x] 7.7 Add verbose logging for startup validation, pipeline execution, and shutdown
- [x] 7.8 Add generous code comments explaining orchestration flow

## 8. FastAPI Application

- [x] 8.1 Create src/aws_connectivity_test/main.py with FastAPI app setup
- [x] 8.2 Implement /health endpoint returning 200 OK when all clients operational, 503 otherwise
- [x] 8.3 Implement lifespan context manager for startup/shutdown coordination
- [x] 8.4 Integrate orchestrator to run Kafka consumer in background
- [x] 8.5 Add verbose logging for application startup and health check requests
- [x] 8.6 Add generous code comments explaining FastAPI integration

## 9. Helm Chart

- [x] 9.1 Create helm/aws-connectivity-test/ directory structure
- [x] 9.2 Create Chart.yaml with ho-microservice dependency (v0.1.15) from ECR OCI registry
- [x] 9.3 Create values.yaml with default configuration (single deployment, no ingress)
- [x] 9.4 Configure ServiceAccount with IRSA annotation placeholder
- [x] 9.5 Configure ExternalSecret for OpenAI API key from AWS Secrets Manager
- [x] 9.6 Configure all environment variables (Kafka, PostgreSQL, OpenSearch, OpenAI, AWS)
- [x] 9.7 Configure health check probes (liveness and readiness) using /health endpoint
- [x] 9.8 Configure resource requests and limits
- [x] 9.9 Configure Service (ClusterIP) with health endpoint port
- [x] 9.10 Set ingress.enabled=false
- [x] 9.11 Add comments in values.yaml explaining configuration sections

## 10. Documentation

- [x] 10.1 Create README.md with project overview, architecture diagram, and features list
- [x] 10.2 Document prerequisites (Python 3.11+, AWS resources, IAM permissions required)
- [x] 10.3 Document local development setup and docker-compose usage
- [x] 10.4 Document environment variable configuration with examples
- [x] 10.5 Document Kubernetes deployment steps with IAM role setup
- [x] 10.6 Document how to verify connectivity via logs
- [x] 10.7 Document troubleshooting common issues (IAM permissions, connection errors)
- [x] 10.8 Add example IAM policies for MSK, RDS, OpenSearch access

## 11. Testing and Validation

- [x] 11.1 Create tests/conftest.py with pytest fixtures for mocked clients
- [x] 11.2 Create tests/test_config.py for configuration validation
- [x] 11.3 ~~Test local development environment with docker-compose~~ (skipped - validated on EKS)
- [x] 11.4 Build Docker image and verify it runs
- [x] 11.5 Deploy helm chart to nonprod environment
- [x] 11.6 Verify startup logs show all AWS connections successful
- [x] 11.7 Produce test message to Kafka topic and verify end-to-end processing
- [x] 11.8 Verify demo_log table contains processed message entries
- [x] 11.9 Verify OpenSearch index contains vector documents
- [x] 11.10 Verify /health endpoint returns 200 OK

## 12. Kafka Producer with MSK IAM Authentication

- [x] 12.1 Create src/aws_connectivity_test/kafka_producer.py with confluent-kafka producer setup
- [x] 12.2 Implement MSK IAM authentication callback using aws-msk-iam-sasl-signer-python
- [x] 12.3 Configure producer with SASL_SSL and IAM auth
- [x] 12.4 Implement async publish method with delivery callback
- [x] 12.5 Add verbose logging for publish operations
- [x] 12.6 Add generous code comments explaining MSK IAM auth flow

## 13. Redis Client with ElastiCache IAM Authentication

- [x] 13.1 Create src/aws_connectivity_test/redis_client.py with redis-py setup
- [x] 13.2 Implement ElastiCacheIAMProvider credential provider using botocore RequestSigner
- [x] 13.3 Implement TTL-cached token generation (15 minute validity)
- [x] 13.4 Implement set_status method for stage tracking
- [x] 13.5 Implement get_status and get_all_statuses methods
- [x] 13.6 Implement health_check method
- [x] 13.7 Add Redis configuration to config.py
- [x] 13.8 Add verbose logging for connection and operations
- [x] 13.9 Add generous code comments explaining IAM auth flow

## 14. API Endpoints for Publishing and Status

- [x] 14.1 Add POST /publish endpoint to main.py
- [x] 14.2 Add GET /status endpoint to main.py
- [x] 14.3 Integrate KafkaProducerClient into orchestrator
- [x] 14.4 Integrate RedisClient into orchestrator
- [x] 14.5 Add Redis status updates at each pipeline stage in _handle_message
- [x] 14.6 Update health_check to include Redis status
- [x] 14.7 Update startup/shutdown to manage new clients

## 15. Helm Configuration for Redis

- [x] 15.1 Add Redis environment variables to values.yaml
- [x] 15.2 Add Redis configuration to nonprod values override
- [x] 15.3 Verify REDIS_HOST and REDIS_PORT from existing secrets mapping
