"""
AWS Connectivity Test Service
=============================

A FastAPI service for testing connectivity to AWS services (MSK, RDS, OpenSearch)
with IAM authentication in Kubernetes environments.

This service validates:
- AWS MSK (Kafka) connectivity with IAM authentication via IRSA
- PostgreSQL RDS connectivity with IAM authentication
- OpenSearch Serverless connectivity with IAM authentication
- OpenAI API connectivity for embedding generation

All operations are logged verbosely to stdout for verification.
"""

__version__ = "0.1.0"
__service_name__ = "aws-connectivity-test"
