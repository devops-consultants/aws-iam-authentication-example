## Context

This service tests AWS connectivity in Kubernetes with IAM authentication. It validates the complete data pipeline: MSK → OpenAI embeddings → OpenSearch → PostgreSQL logging. The existing `data-ingest` application provides proven MSK IAM patterns, and `hyperoptic-ota` helm chart demonstrates IRSA configuration with the `ho-microservice` base chart.

**Current State**: Manual testing of AWS service connectivity requires separate validation of each service, making deployment verification slow and error-prone.

**Constraints**:
- Must use AWS IAM authentication (IRSA) for all AWS services
- Must follow existing patterns from `data-ingest` and `helm/hyperoptic-ota`
- Verbose logging required for operation verification
- Runs as long-lived Kubernetes deployment (not a job)
- Must inherit `ho-microservice` helm chart (v0.1.15)

**Stakeholders**: Platform team, DevOps, developers validating AWS connectivity in non-prod/prod environments.

## Goals / Non-Goals

**Goals:**
- Single service testing MSK, RDS (PostgreSQL), OpenSearch Serverless, and OpenAI connectivity
- IAM authentication for all AWS services using IRSA
- Verbose logging documenting all operations for verification
- Helm deployment inheriting `ho-microservice` with environment-specific configuration
- Health endpoints for Kubernetes probes
- Generously commented code for clarity

**Non-Goals:**
- Production data processing (this is a test/validation service)
- High-performance optimization (focus is on clear logging and connectivity validation)
- Complex error recovery (basic retry logic only)
- Unit test coverage (integration testing via deployment validation)
- Database migrations or schema management (creates simple demo table)

## Decisions

### 1. Application Structure: FastAPI with Async I/O

**Decision**: Use FastAPI with asyncio for concurrent AWS service operations.

**Rationale**:
- FastAPI provides health endpoints required by Kubernetes probes
- Async I/O allows concurrent initialization of multiple AWS clients
- Consistent with modern Python service patterns
- `/health` endpoint enables liveness/readiness checks

**Alternatives Considered**:
- Pure Python script: Lacks health endpoint infrastructure
- Flask: Synchronous model less efficient for I/O-bound operations

### 2. Service Lifecycle: Startup Connection + Continuous Consumption

**Decision**: Connect to all AWS services on startup, then continuously consume Kafka messages.

**Rationale**:
- Startup connection tests validate IAM permissions immediately
- Continuous consumption allows repeated testing without pod restarts
- Verbose logging during startup shows connection status clearly
- Follows `data-ingest` application pattern

**Flow**:
1. Service starts → verbose logging begins
2. Connect PostgreSQL (IAM auth) → create `demo_log` table if needed
3. Connect OpenSearch Serverless (IAM auth) → verify endpoint reachable
4. Connect Kafka (IAM auth) → create consumer group, subscribe to topics
5. Start consuming messages → for each message:
   - Call OpenAI to generate embedding
   - Write embedding to OpenSearch vector index
   - Log operation details to PostgreSQL `demo_log` table
   - Emit verbose logs to stdout

### 3. MSK Consumer: Reuse data-ingest Patterns

**Decision**: Adapt MSK IAM authentication code from `data-ingest/src/proactive_comms_data_ingest/kafka_consumer.py`.

**Rationale**:
- Proven implementation of `aws-msk-iam-sasl-signer-python`
- Handles consumer group management correctly
- Includes proper shutdown handling for Kubernetes

**Key Components**:
- `aiokafka.AIOKafkaConsumer` with IAM auth callback
- Consumer group configuration
- Topic subscription from environment variables
- Graceful shutdown on SIGTERM

### 4. PostgreSQL: IAM Authentication with asyncpg

**Decision**: Use `asyncpg` with AWS RDS IAM token generation.

**Rationale**:
- Async driver matches FastAPI's async architecture
- IAM token generation via `boto3.client('rds').generate_db_auth_token()`
- Tokens rotate automatically (15-minute validity)
- Pattern used in `hyperoptic-ota` backend (`POSTGRESQL_USE_IAM_AUTH=true`)

**Schema**:
```sql
CREATE TABLE IF NOT EXISTS demo_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    kafka_topic TEXT NOT NULL,
    kafka_partition INT NOT NULL,
    kafka_offset BIGINT NOT NULL,
    message_content TEXT,
    embedding_model TEXT,
    embedding_dimensions INT,
    opensearch_index TEXT,
    opensearch_doc_id TEXT,
    log_level TEXT DEFAULT 'INFO'
);
```

### 5. OpenSearch: IAM Signature v4 with opensearchpy

**Decision**: Use `opensearchpy` with AWS SigV4 request signing for IAM authentication.

**Rationale**:
- Official OpenSearch Python client
- AWS request signing via `boto3` credentials
- Pattern used in `hyperoptic-ota` backend (`OPENSEARCH_USE_IAM_AUTH=true`)

**Configuration**:
- Use `RequestsHttpConnection` with AWS4Auth
- Get credentials from boto3 session (IRSA provides these)
- Write embeddings as vectors with metadata

### 6. OpenAI Client: Standard SDK with API Key from Secrets

**Decision**: Use official `openai` Python SDK with API key from AWS Secrets Manager.

**Rationale**:
- Standard approach, well-documented
- API key stored in AWS Secrets Manager (referenced in helm chart)
- Model name configurable via environment variable

**Usage**:
```python
from openai import AsyncOpenAI
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
embedding = await client.embeddings.create(
    model=os.getenv("OPENAI_EMBEDDING_MODEL"),
    input=message_text
)
```

### 7. Helm Chart: Inherit ho-microservice Like hyperoptic-ota

**Decision**: Create `helm/aws-connectivity-test/` inheriting `ho-microservice` chart.

**Rationale**:
- Consistent with existing deployment patterns
- `ho-microservice` provides ServiceAccount, Deployment, Service, ConfigMap, ExternalSecret
- Reference implementation: `helm/hyperoptic-ota/Chart.yaml` and `values.yaml`

**Key Configuration**:
- Single deployment (no frontend/backend/scheduler split like hyperoptic-ota)
- ServiceAccount with IRSA annotation
- ExternalSecret for OpenAI API key
- Environment variables for AWS endpoints and configuration
- Health check endpoints: `/health` (liveness and readiness)
- No ingress required (internal service)

### 8. Logging Strategy: Structured JSON with Verbose Operation Details

**Decision**: Use `structlog` for JSON structured logging with verbose operation tracking.

**Rationale**:
- JSON logs parse easily in CloudWatch/Grafana
- Structured fields enable filtering and searching
- Consistent with `data-ingest` logging patterns
- Each operation logs: timestamp, service, action, status, details

**Log Events**:
- Service startup
- AWS client initialization (PostgreSQL, OpenSearch, Kafka, OpenAI)
- Kafka message consumed
- OpenAI embedding generated
- OpenSearch document written
- PostgreSQL log inserted
- Errors and retries

## Risks / Trade-offs

**[Risk] IAM permissions misconfigured → Service fails to connect**
- Mitigation: Verbose logging shows exact permission errors; document required IAM policies in README

**[Risk] Kafka topic has no messages → Service appears idle**
- Mitigation: Log periodic heartbeat showing consumer is active; document test message production

**[Risk] OpenAI API rate limits → Embedding generation fails**
- Mitigation: Log rate limit errors clearly; document as expected behavior in README

**[Risk] Long-running consumer → Memory growth**
- Mitigation: Use async I/O to minimize memory; document as test service not optimized for production loads

**[Risk] Multiple services to configure → Complex environment variables**
- Mitigation: Provide clear `.env.example` and comprehensive README; follow patterns from `data-ingest`

**[Trade-off] Verbose logging → Higher CloudWatch costs**
- Acceptable: This is a test service, clarity over cost

**[Trade-off] No retry logic → Failures require manual restart**
- Acceptable: Test service prioritizes clear failure visibility over resilience

## Migration Plan

**Deployment Steps**:

1. **Build Docker image**:
   - Create `aws-connectivity-test/` directory with application code
   - Dockerfile based on `data-ingest/Dockerfile` pattern
   - Build and push to ECR: `538189757816.dkr.ecr.eu-west-2.amazonaws.com/pc/proactive-comms/aws-connectivity-test`

2. **Configure IAM role**:
   - Create IAM role for service account (IRSA)
   - Attach policies for MSK, RDS, OpenSearch access
   - Reference in helm chart ServiceAccount annotation

3. **Store secrets**:
   - Store OpenAI API key in AWS Secrets Manager
   - Configure ExternalSecret in helm chart

4. **Deploy helm chart**:
   - Create environment-specific values files (nonprod, prod)
   - Configure KAFKA_BOOTSTRAP_SERVERS, POSTGRES_HOST, OPENSEARCH_ENDPOINT
   - Deploy to nonprod first for validation

5. **Verify deployment**:
   - Check pod logs for startup sequence and AWS connections
   - Produce test message to Kafka topic
   - Verify message processing in logs
   - Check PostgreSQL `demo_log` table for entries
   - Check OpenSearch index for vector documents

**Rollback Strategy**:
- Delete helm release: `helm delete aws-connectivity-test`
- No database state to clean up (demo table is isolated)
- No data loss risk (test service only)

## Open Questions

- **Q**: Which nonprod environment should be used for initial testing?
  - **A**: TBD based on platform team guidance

- **Q**: Should the service run continuously or as a cron job?
  - **A**: Continuous deployment (decided above) for repeated testing without restarts

- **Q**: Which OpenAI embedding model should be the default?
  - **A**: `text-embedding-3-small` (configurable via environment variable)
