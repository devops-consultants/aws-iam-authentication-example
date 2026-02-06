# AWS Connectivity Test Service

A FastAPI service for testing connectivity to AWS services (MSK, RDS, OpenSearch Serverless) with IAM authentication in Kubernetes environments.

## Overview

This service validates the complete data pipeline by:
1. **Consuming** messages from AWS MSK (Kafka) using IAM authentication
2. **Generating** embeddings using OpenAI's embedding models
3. **Storing** vectors in AWS OpenSearch Serverless with IAM authentication
4. **Logging** operations to AWS RDS (PostgreSQL) with IAM authentication

All operations are logged verbosely to stdout, making it easy to verify connectivity in deployment logs.

## Architecture

```
┌─────────────────┐
│   AWS MSK       │
│  (Kafka Topics) │
└────────┬────────┘
         │
         │ SASL_SSL + IAM Auth (IRSA)
         │
    ┌────▼────────────────────┐
    │  AWS Connectivity Test  │
    │  Service                │
    │                         │
    │  ┌──────────────────┐   │
    │  │ Message Pipeline │   │
    │  │ Consume → Embed  │   │
    │  │ → Store → Log    │   │
    │  └──────────────────┘   │
    └────────┬────────────────┘
             │
    ┌────────┼────────┬───────────────┐
    │        │        │               │
    ▼        ▼        ▼               ▼
┌───────┐ ┌───────┐ ┌───────────┐ ┌──────────┐
│OpenAI │ │OpenSrch│ │PostgreSQL │ │CloudWatch│
│ API   │ │Serverls│ │   RDS     │ │  Logs    │
└───────┘ └───────┘ └───────────┘ └──────────┘
```

## Features

- **AWS MSK IAM Authentication**: Native support for MSK IAM auth via `aws-msk-iam-sasl-signer`
- **PostgreSQL IAM Authentication**: RDS IAM database authentication token generation
- **OpenSearch IAM Authentication**: SigV4 request signing for OpenSearch Serverless
- **OpenAI Integration**: Embedding generation with configurable models
- **Verbose Logging**: JSON structured logs documenting all operations
- **Health Endpoints**: Kubernetes-compatible liveness and readiness probes
- **Graceful Shutdown**: Proper signal handling for clean pod termination
- **Helm Deployment**: Ready-to-deploy Helm chart inheriting `ho-microservice`

## Prerequisites

### Software Requirements

- Python 3.11+
- Docker (for local development and building images)
- Helm 3.x (for Kubernetes deployment)
- kubectl (for Kubernetes management)

### AWS Resources

Before deploying, you need:

| Resource | Description |
|----------|-------------|
| AWS MSK Cluster | Kafka cluster with IAM authentication enabled |
| AWS RDS PostgreSQL | Database instance with IAM authentication enabled |
| AWS OpenSearch Serverless | Collection with IAM access configured |
| OpenAI API Key | Stored in AWS Secrets Manager |
| IAM Role | Role for IRSA with policies for MSK, RDS, OpenSearch |

### Required IAM Permissions

The service's IAM role needs these permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "MSKConnect",
            "Effect": "Allow",
            "Action": [
                "kafka-cluster:Connect",
                "kafka-cluster:DescribeCluster"
            ],
            "Resource": "arn:aws:kafka:eu-west-2:ACCOUNT:cluster/CLUSTER_NAME/*"
        },
        {
            "Sid": "MSKTopics",
            "Effect": "Allow",
            "Action": [
                "kafka-cluster:ReadData",
                "kafka-cluster:DescribeTopic"
            ],
            "Resource": "arn:aws:kafka:eu-west-2:ACCOUNT:topic/CLUSTER_NAME/*"
        },
        {
            "Sid": "MSKGroups",
            "Effect": "Allow",
            "Action": [
                "kafka-cluster:AlterGroup",
                "kafka-cluster:DescribeGroup"
            ],
            "Resource": "arn:aws:kafka:eu-west-2:ACCOUNT:group/CLUSTER_NAME/*"
        },
        {
            "Sid": "RDSConnect",
            "Effect": "Allow",
            "Action": "rds-db:connect",
            "Resource": "arn:aws:rds-db:eu-west-2:ACCOUNT:dbuser:DB_RESOURCE_ID/connectivity_test"
        },
        {
            "Sid": "OpenSearchAccess",
            "Effect": "Allow",
            "Action": "aoss:APIAccessAll",
            "Resource": "arn:aws:aoss:eu-west-2:ACCOUNT:collection/COLLECTION_ID"
        },
        {
            "Sid": "SecretsAccess",
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret"
            ],
            "Resource": "arn:aws:secretsmanager:eu-west-2:ACCOUNT:secret:aws-connectivity-test-*"
        }
    ]
}
```

## Quick Start

### Local Development

1. **Clone and navigate to the project:**

   ```bash
   cd aws-connectivity-test
   ```

2. **Set up the development environment:**

   ```bash
   ./scripts/local-dev.sh setup
   ```

3. **Configure environment variables:**

   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. **Start the local development stack:**

   ```bash
   ./scripts/local-dev.sh start
   ```

   This starts:
   - Kafka (localhost:9092)
   - Zookeeper (localhost:2181)
   - PostgreSQL (localhost:5432)
   - Connectivity test application (localhost:8080)

5. **View logs:**

   ```bash
   ./scripts/local-dev.sh logs
   ```

6. **Send a test message:**

   ```bash
   ./scripts/local-dev.sh kafka-send test-topic "Hello, World!"
   ```

7. **Stop the stack:**

   ```bash
   ./scripts/local-dev.sh stop
   ```

### Development Helper Script

The `scripts/local-dev.sh` script provides convenient commands:

```bash
./scripts/local-dev.sh setup       # Set up development environment
./scripts/local-dev.sh start       # Start docker-compose stack
./scripts/local-dev.sh stop        # Stop docker-compose stack
./scripts/local-dev.sh logs        # Show application logs
./scripts/local-dev.sh test        # Run test suite
./scripts/local-dev.sh lint        # Run linters
./scripts/local-dev.sh format      # Format code
./scripts/local-dev.sh build       # Build Docker image
./scripts/local-dev.sh psql        # Connect to PostgreSQL
./scripts/local-dev.sh kafka-send  # Send test message
./scripts/local-dev.sh clean       # Clean up environment
```

## Configuration

Configuration is managed through environment variables. See `.env.example` for all options.

### Kafka / AWS MSK Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker addresses | `localhost:9092` |
| `KAFKA_TOPICS` | Topics to consume (comma-separated) | `test-topic` |
| `KAFKA_CONSUMER_GROUP` | Consumer group ID | `connectivity-test` |
| `KAFKA_SECURITY_PROTOCOL` | Security protocol | `PLAINTEXT` |
| `KAFKA_USE_IAM_AUTH` | Enable MSK IAM auth | `false` |

### PostgreSQL / AWS RDS Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_HOST` | Database host | `localhost` |
| `POSTGRES_PORT` | Database port | `5432` |
| `POSTGRES_DB` | Database name | `connectivity_test` |
| `POSTGRES_USER` | Database user | `postgres` |
| `POSTGRESQL_USE_IAM_AUTH` | Enable RDS IAM auth | `false` |

### OpenSearch Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENSEARCH_ENDPOINT` | OpenSearch endpoint URL | `http://localhost:9200` |
| `OPENSEARCH_INDEX` | Index for storing vectors | `connectivity-test-vectors` |
| `OPENSEARCH_USE_IAM_AUTH` | Enable IAM auth (SigV4) | `false` |
| `OPENSEARCH_ENABLED` | Enable OpenSearch | `true` |

### OpenAI Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | (required) |
| `OPENAI_EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` |
| `OPENAI_ENABLED` | Enable OpenAI | `true` |

### Application Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level | `INFO` |
| `LOG_FORMAT` | Log format (json/console) | `json` |
| `AWS_REGION` | AWS region | `eu-west-2` |
| `SHUTDOWN_TIMEOUT` | Graceful shutdown timeout | `30` |

## Kubernetes Deployment

### Prerequisites

1. EKS cluster with IRSA configured
2. External Secrets Operator installed
3. `ho-microservice` chart available in ECR

### Deployment Steps

1. **Create IAM role for IRSA:**

   Create an IAM role with the policies above and trust relationship:

   ```json
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Principal": {
                   "Federated": "arn:aws:iam::ACCOUNT:oidc-provider/oidc.eks.REGION.amazonaws.com/id/OIDC_ID"
               },
               "Action": "sts:AssumeRoleWithWebIdentity",
               "Condition": {
                   "StringEquals": {
                       "oidc.eks.REGION.amazonaws.com/id/OIDC_ID:sub": "system:serviceaccount:NAMESPACE:aws-connectivity-test"
                   }
               }
           }
       ]
   }
   ```

2. **Store OpenAI API key in Secrets Manager:**

   ```bash
   aws secretsmanager create-secret \
       --name aws-connectivity-test-openai-credentials \
       --secret-string '{"OPENAI_API_KEY": "sk-your-key-here"}'
   ```

3. **Create environment-specific values file:**

   ```yaml
   # values-nonprod.yaml
   connectivity-test:
     serviceAccount:
       annotations:
         eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT:role/aws-connectivity-test-role

     extraEnv:
       - name: KAFKA_BOOTSTRAP_SERVERS
         value: b-1.your-msk-cluster.kafka.eu-west-2.amazonaws.com:9098
       - name: POSTGRES_HOST
         value: your-db.cluster-xxxx.eu-west-2.rds.amazonaws.com
       - name: OPENSEARCH_ENDPOINT
         value: https://xxxxx.eu-west-2.aoss.amazonaws.com
   ```

4. **Deploy with Helm:**

   ```bash
   helm dependency update ./helm/aws-connectivity-test
   helm upgrade --install aws-connectivity-test ./helm/aws-connectivity-test \
       -f ./helm/aws-connectivity-test/values.yaml \
       -f ./helm/aws-connectivity-test/values-nonprod.yaml \
       -n your-namespace
   ```

### Verifying Deployment

1. **Check pod status:**

   ```bash
   kubectl get pods -l app.kubernetes.io/name=aws-connectivity-test
   ```

2. **View startup logs:**

   ```bash
   kubectl logs -l app.kubernetes.io/name=aws-connectivity-test -f
   ```

   Look for the startup sequence:
   ```
   STARTING AWS CONNECTIVITY TEST SERVICE
   Step 1/4: Connecting to PostgreSQL...
   ✓ PostgreSQL connection successful
   Step 2/4: Connecting to OpenSearch...
   ✓ OpenSearch connection successful
   Step 3/4: Initializing OpenAI...
   ✓ OpenAI initialization successful
   Step 4/4: Connecting to Kafka...
   ✓ Kafka connection successful
   STARTUP COMPLETE - ALL SERVICES CONNECTED
   ```

3. **Check health endpoint:**

   ```bash
   kubectl port-forward svc/aws-connectivity-test 8080:8080
   curl http://localhost:8080/health
   ```

4. **Produce test message:**

   Use your Kafka producer to send a message to the configured topic.

5. **Verify processing in logs:**

   ```bash
   kubectl logs -l app.kubernetes.io/name=aws-connectivity-test | grep "Message pipeline complete"
   ```

6. **Check PostgreSQL demo_log table:**

   Connect to your database and query:
   ```sql
   SELECT * FROM demo_log ORDER BY timestamp DESC LIMIT 10;
   ```

## Troubleshooting

### MSK Connection Failures

**Symptom**: `KafkaConnectionError: Failed to connect to Kafka`

**Solutions**:
- Verify IAM role has `kafka-cluster:Connect` permission
- Check security group allows traffic from EKS nodes to MSK
- Verify `KAFKA_BOOTSTRAP_SERVERS` uses port 9098 (IAM) not 9092
- Check IRSA is configured correctly (`eks.amazonaws.com/role-arn` annotation)

### RDS Connection Failures

**Symptom**: `PostgresConnectionError: Failed to connect to PostgreSQL`

**Solutions**:
- Verify IAM role has `rds-db:connect` permission for the user
- Check database has IAM authentication enabled
- Verify security group allows traffic from EKS nodes
- Check the database user exists and is configured for IAM auth

### OpenSearch Connection Failures

**Symptom**: `OpenSearchConnectionError: Failed to connect to OpenSearch`

**Solutions**:
- Verify IAM role has `aoss:APIAccessAll` permission for the collection
- Check the collection data access policy allows the IAM role
- Verify endpoint URL is correct (includes `https://`)
- Check VPC endpoints if using private access

### OpenAI API Errors

**Symptom**: `OpenAIEmbeddingError: Rate limit exceeded`

**Solutions**:
- Check API key is valid and has credits
- Consider using a smaller embedding model
- Reduce `MAX_CONCURRENT_MESSAGES` to limit concurrent API calls

## Version

Current version: **0.1.0**

Version is managed in `pyproject.toml` and `Chart.yaml`.

## License

Copyright © 2025 Hyperoptic. All rights reserved.

## Support

For issues or questions:
- Create a Jira issue
- Contact the platform team
- Check internal documentation
