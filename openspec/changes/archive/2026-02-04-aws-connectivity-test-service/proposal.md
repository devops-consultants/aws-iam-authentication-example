## Why

Testing AWS service connectivity in Kubernetes environments with IAM-based authentication is currently a manual, time-consuming process. This change creates a purpose-built test service that validates connectivity to AWS MSK (Kafka), PostgreSQL RDS, and OpenSearch Serverless in a single deployment, with verbose logging that makes verification simple and auditable. This is needed now to support faster deployment validation and troubleshooting across non-production and production environments.

## What Changes

- **New Python FastAPI application** for AWS connectivity testing with verbose logging
- **AWS MSK (Kafka) consumer** using IAM authentication via IRSA, consuming messages from configurable topics
- **OpenAI embeddings integration** to generate vector embeddings from Kafka messages
- **OpenSearch Serverless client** using IAM authentication to write vector embeddings to a configurable index
- **PostgreSQL RDS client** using IAM authentication to create and write to a demo-log table
- **Helm chart** inheriting `ho-microservice` for Kubernetes deployment with IRSA-enabled service account
- **Health check endpoints** for liveness and readiness probes
- **Comprehensive logging** to stdout documenting all connectivity attempts and operations

## Capabilities

### New Capabilities
- `aws-msk-iam-consumer`: AWS MSK Kafka consumer with IAM authentication, consumer group management, and configurable topic consumption
- `openai-embeddings-client`: OpenAI API client for generating embeddings from text content with configurable model selection
- `opensearch-vector-writer`: OpenSearch Serverless client with IAM authentication for writing vector embeddings to indices
- `postgres-iam-client`: PostgreSQL RDS client with IAM authentication for table creation and data insertion
- `connectivity-test-orchestrator`: Service orchestration that coordinates message consumption, embedding generation, vector storage, and database logging with verbose operation tracking
- `connectivity-test-helm`: Helm chart for Kubernetes deployment with IRSA, environment configuration, and health checks

### Modified Capabilities
<!-- No existing capabilities are being modified -->

## Impact

**New Code**:
- New Python application at `aws-connectivity-test/` (similar structure to `data-ingest/`)
- New Helm chart at `helm/aws-connectivity-test/`

**Reference Implementations**:
- MSK connectivity patterns from `data-ingest/` application
- Helm deployment patterns from `helm/hyperoptic-ota/`
- IAM authentication configuration from `helm/hyperoptic-ota/values.yaml`

**Dependencies**:
- Python 3.11+
- FastAPI framework
- `aiokafka` with `aws-msk-iam-sasl-signer-python` for MSK IAM auth
- `openai` Python client
- `opensearchpy` with AWS request signing
- `asyncpg` with AWS RDS IAM token generation
- `ho-microservice` Helm chart (v0.1.15 or compatible)

**AWS Resources**:
- Requires access to AWS MSK cluster
- Requires access to PostgreSQL RDS instance
- Requires access to OpenSearch Serverless collection
- Requires OpenAI API key (stored in AWS Secrets Manager)
- Requires IAM role with policies for MSK, RDS, and OpenSearch access

**Environment Variables** (all configurable):
- Kafka bootstrap servers, topics, consumer group
- OpenAI model name and API credentials
- OpenSearch endpoint and index name
- PostgreSQL connection details
- AWS region configuration
