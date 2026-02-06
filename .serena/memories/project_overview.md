# AWS Connectivity Test Service - Project Overview

## Purpose
A FastAPI service for testing connectivity to AWS services (MSK, RDS, OpenSearch Serverless, ElastiCache) with IAM authentication in Kubernetes environments.

## What It Does
1. **Consumes** messages from AWS MSK (Kafka) using IAM authentication
2. **Generates** embeddings using OpenAI's embedding models
3. **Stores** vectors in AWS OpenSearch Serverless with IAM authentication
4. **Logs** operations to AWS RDS (PostgreSQL) with IAM authentication
5. **Tracks** status in AWS ElastiCache (Redis) with IAM authentication

## Tech Stack
- **Language**: Python 3.11+
- **Web Framework**: FastAPI with Uvicorn
- **Async Kafka**: aiokafka with aws-msk-iam-sasl-signer-python
- **Database**: asyncpg for PostgreSQL
- **Search**: opensearch-py with AWS4Auth for OpenSearch Serverless
- **Cache**: Redis with IAM authentication for ElastiCache
- **AI**: OpenAI client for embeddings
- **AWS SDK**: boto3 for IAM authentication
- **Configuration**: pydantic-settings
- **Logging**: structlog (JSON structured logs)
- **Testing**: pytest with pytest-asyncio
- **Linting**: black, flake8, mypy, isort

## Project Structure
```
aws-connectivity-test/
├── src/aws_connectivity_test/    # Main application code
│   ├── main.py                   # FastAPI application entry point
│   ├── config.py                 # Pydantic Settings configuration
│   ├── orchestrator.py           # Message processing orchestration
│   ├── kafka_consumer.py         # Kafka consumer with IAM auth
│   ├── kafka_producer.py         # Kafka producer
│   ├── postgres_client.py        # PostgreSQL client with IAM auth
│   ├── opensearch_client.py      # OpenSearch client with SigV4
│   ├── redis_client.py           # Redis client with IAM auth
│   ├── openai_client.py          # OpenAI embeddings client
│   ├── exceptions.py             # Custom exceptions
│   └── logging_config.py         # Structured logging setup
├── tests/                        # Test suite
├── scripts/
│   └── local-dev.sh              # Development helper script
├── pyproject.toml                # Project configuration
├── docker-compose.yml            # Local development stack
└── Dockerfile                    # Container image
```

## Deployment
- Kubernetes with Helm charts
- IRSA (IAM Roles for Service Accounts) for AWS authentication
- External Secrets Operator for secrets management
