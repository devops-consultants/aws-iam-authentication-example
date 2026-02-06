## ADDED Requirements

### Requirement: Service startup sequence

The system SHALL initialize all AWS clients in a defined sequence on startup: PostgreSQL → OpenSearch → Kafka → OpenAI.

#### Scenario: Successful startup

- **WHEN** service starts with valid configuration
- **THEN** all clients initialize successfully in order with verbose logging

#### Scenario: Startup failure

- **WHEN** any client fails to initialize
- **THEN** service logs clear error and exits with non-zero code

### Requirement: Message processing pipeline

The system SHALL orchestrate the complete message processing pipeline: consume Kafka message → generate embedding → write to OpenSearch → log to PostgreSQL.

#### Scenario: Successful message processing

- **WHEN** Kafka message is consumed
- **THEN** pipeline executes all steps and logs success

#### Scenario: Pipeline failure at any step

- **WHEN** any pipeline step fails
- **THEN** error is logged with step details and message is not committed

### Requirement: Verbose operation tracking

The system SHALL log every operation with timestamp, operation type, status, and detailed context.

#### Scenario: Operation logging

- **WHEN** any operation executes (connection, consumption, API call, write)
- **THEN** log includes: timestamp, operation name, status (started/completed/failed), duration, relevant metadata

### Requirement: Health check endpoint

The system SHALL expose /health endpoint returning 200 OK when all clients are initialized and operational.

#### Scenario: Healthy service

- **WHEN** all clients are connected and operational
- **THEN** /health returns 200 OK with status details

#### Scenario: Unhealthy service

- **WHEN** any client is disconnected or failing
- **THEN** /health returns 503 Service Unavailable with failure details

### Requirement: Graceful shutdown coordination

The system SHALL coordinate graceful shutdown across all clients when SIGTERM is received.

#### Scenario: Shutdown sequence

- **WHEN** SIGTERM is received
- **THEN** service stops consuming, closes all client connections in order (Kafka → PostgreSQL → OpenSearch), and exits within timeout

### Requirement: Startup validation logging

The system SHALL log comprehensive startup validation confirming all AWS services are reachable.

#### Scenario: Startup validation

- **WHEN** service starts
- **THEN** log includes: environment variables (masked), IAM role, AWS region, all service endpoints, connection status for each service

### Requirement: Message processing metrics in logs

The system SHALL log processing metrics for each message including latencies for each operation.

#### Scenario: Message metrics

- **WHEN** message is processed
- **THEN** log includes: total processing time, embedding generation time, OpenSearch write time, PostgreSQL insert time

### Requirement: Error context preservation

The system SHALL preserve full error context when operations fail for debugging.

#### Scenario: Error logging

- **WHEN** any operation fails
- **THEN** log includes: error type, error message, stack trace, operation context (message ID, topic, etc.)

### Requirement: Concurrent message handling

The system SHALL process messages concurrently using async I/O with configurable concurrency limit.

#### Scenario: Concurrent processing

- **WHEN** multiple messages are available
- **THEN** up to N messages (configured limit) are processed concurrently

#### Scenario: Concurrency limit

- **WHEN** concurrency limit is reached
- **THEN** additional messages wait until processing slots are available

### Requirement: Service identification in logs

The system SHALL include service name and version in all log entries for identification.

#### Scenario: Log structure

- **WHEN** any log is emitted
- **THEN** log includes: service="aws-connectivity-test", version=<version>, environment=<env>
