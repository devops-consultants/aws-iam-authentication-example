## ADDED Requirements

### Requirement: ho-microservice chart inheritance

The system SHALL use ho-microservice chart (v0.1.15 or compatible) as dependency for deployment infrastructure.

#### Scenario: Chart dependency

- **WHEN** helm chart is defined
- **THEN** Chart.yaml includes ho-microservice as dependency from ECR OCI registry

### Requirement: IRSA-enabled service account

The system SHALL create a Kubernetes ServiceAccount with IAM role annotation for IRSA authentication.

#### Scenario: ServiceAccount with IRSA

- **WHEN** helm chart is deployed
- **THEN** ServiceAccount includes eks.amazonaws.com/role-arn annotation with IAM role ARN

### Requirement: ExternalSecret for OpenAI credentials

The system SHALL use ExternalSecret to fetch OpenAI API key from AWS Secrets Manager.

#### Scenario: Secret configuration

- **WHEN** helm chart is deployed
- **THEN** ExternalSecret is created referencing AWS Secrets Manager path for OpenAI credentials

#### Scenario: Secret mounting

- **WHEN** pod starts
- **THEN** OpenAI API key is available as environment variable OPENAI_API_KEY

### Requirement: Environment-specific configuration

The system SHALL support environment-specific values files for nonprod and prod deployments.

#### Scenario: Nonprod deployment

- **WHEN** deployed with nonprod values
- **THEN** uses nonprod-specific: Kafka bootstrap servers, RDS endpoint, OpenSearch endpoint, IAM role

#### Scenario: Prod deployment

- **WHEN** deployed with prod values
- **THEN** uses prod-specific endpoints and IAM role

### Requirement: Required environment variables

The system SHALL configure all required environment variables via helm values.

#### Scenario: Kafka configuration

- **WHEN** helm chart is deployed
- **THEN** pod includes: KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPICS, KAFKA_CONSUMER_GROUP, KAFKA_SECURITY_PROTOCOL=SASL_SSL

#### Scenario: Database configuration

- **WHEN** helm chart is deployed
- **THEN** pod includes: POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRESQL_USE_IAM_AUTH=true

#### Scenario: OpenSearch configuration

- **WHEN** helm chart is deployed
- **THEN** pod includes: OPENSEARCH_ENDPOINT, OPENSEARCH_INDEX, OPENSEARCH_USE_IAM_AUTH=true

#### Scenario: OpenAI configuration

- **WHEN** helm chart is deployed
- **THEN** pod includes: OPENAI_EMBEDDING_MODEL (default: text-embedding-3-small)

#### Scenario: AWS configuration

- **WHEN** helm chart is deployed
- **THEN** pod includes: AWS_REGION (default: eu-west-2)

### Requirement: Health check probes

The system SHALL configure liveness and readiness probes using /health endpoint.

#### Scenario: Liveness probe

- **WHEN** pod is running
- **THEN** liveness probe checks /health with initial delay and period configured

#### Scenario: Readiness probe

- **WHEN** pod is starting
- **THEN** readiness probe checks /health with initial delay and period configured

### Requirement: Resource limits

The system SHALL define resource requests and limits for the pod.

#### Scenario: Resource configuration

- **WHEN** helm chart is deployed
- **THEN** pod includes: memory requests/limits, CPU requests/limits (configurable)

### Requirement: Deployment configuration

The system SHALL deploy as a Kubernetes Deployment with configurable replica count.

#### Scenario: Single replica deployment

- **WHEN** deployed with default configuration
- **THEN** replicaCount=1

#### Scenario: Multiple replicas

- **WHEN** deployed with replicaCount>1
- **THEN** all replicas join same consumer group and participate in partition assignment

### Requirement: Image configuration

The system SHALL use image from ECR with configurable tag.

#### Scenario: Image specification

- **WHEN** helm chart is deployed
- **THEN** uses image: 538189757816.dkr.ecr.eu-west-2.amazonaws.com/pc/proactive-comms/aws-connectivity-test with pullPolicy configurable

### Requirement: No ingress requirement

The system SHALL not create Ingress resource (internal service only).

#### Scenario: Ingress disabled

- **WHEN** helm chart is deployed
- **THEN** ingress.enabled=false

### Requirement: Service configuration

The system SHALL create a ClusterIP Service exposing the health endpoint.

#### Scenario: Service creation

- **WHEN** helm chart is deployed
- **THEN** Service is created with targetPort matching container port for /health endpoint

### Requirement: Logging configuration

The system SHALL configure structured JSON logging for CloudWatch integration.

#### Scenario: Log format

- **WHEN** pod starts
- **THEN** LOG_FORMAT=json, LOG_LEVEL configurable (default: INFO)

### Requirement: Chart metadata

The system SHALL define chart metadata following organizational conventions.

#### Scenario: Chart.yaml structure

- **WHEN** chart is defined
- **THEN** includes: name=aws-connectivity-test, version, appVersion, description, type=application
