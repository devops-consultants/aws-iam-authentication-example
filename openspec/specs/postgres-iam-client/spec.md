## ADDED Requirements

### Requirement: PostgreSQL IAM authentication

The system SHALL authenticate to PostgreSQL RDS using IAM authentication tokens generated via AWS RDS API.

#### Scenario: Successful IAM authentication

- **WHEN** service starts with valid IAM credentials from IRSA
- **THEN** PostgreSQL client generates IAM token and successfully connects

#### Scenario: Missing IAM credentials

- **WHEN** service starts without IAM credentials
- **THEN** authentication fails with clear error logged

### Requirement: IAM token refresh

The system SHALL refresh IAM authentication tokens before expiry (tokens valid for 15 minutes).

#### Scenario: Token refresh before expiry

- **WHEN** IAM token is nearing expiry
- **THEN** client generates new token and refreshes connection

### Requirement: Database configuration

The system SHALL use PostgreSQL connection details from environment variables: POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER.

#### Scenario: Valid connection details

- **WHEN** all required environment variables are set
- **THEN** client connects successfully to the specified database

#### Scenario: Missing configuration

- **WHEN** required environment variables are missing
- **THEN** service fails to start with clear error message

### Requirement: Demo log table creation

The system SHALL create the demo_log table if it does not exist on startup.

#### Scenario: Table does not exist

- **WHEN** service starts and demo_log table does not exist
- **THEN** table is created with required schema (id, timestamp, kafka_topic, kafka_partition, kafka_offset, message_content, embedding_model, embedding_dimensions, opensearch_index, opensearch_doc_id, log_level)

#### Scenario: Table exists

- **WHEN** service starts and demo_log table exists
- **THEN** table creation is skipped and logged

### Requirement: Log entry insertion

The system SHALL insert log entries documenting each processed message with full operation details.

#### Scenario: Insert successful operation log

- **WHEN** message is successfully processed (embedded and written to OpenSearch)
- **THEN** log entry is inserted with: Kafka metadata, message content, embedding details, OpenSearch details, timestamp

#### Scenario: Insert failure log

- **WHEN** message processing fails
- **THEN** log entry is inserted with error details and log_level='ERROR'

### Requirement: Async database operations

The system SHALL use asyncpg for async PostgreSQL operations to avoid blocking.

#### Scenario: Concurrent inserts

- **WHEN** multiple messages are being processed
- **THEN** database inserts execute concurrently without blocking

### Requirement: Connection pool management

The system SHALL manage a connection pool with configurable size to handle concurrent operations efficiently.

#### Scenario: Pool configuration

- **WHEN** service starts
- **THEN** connection pool is created with configured min/max connections

#### Scenario: Pool exhaustion

- **WHEN** all pool connections are in use
- **THEN** new operations wait for available connection with timeout

### Requirement: Connection initialization logging

The system SHALL log database connection initialization with configuration details.

#### Scenario: Connection startup

- **WHEN** service starts
- **THEN** log includes: host (masked), port, database name, user, IAM auth status, connection success

### Requirement: Schema validation

The system SHALL verify the demo_log table schema matches expected structure on startup.

#### Scenario: Schema validation

- **WHEN** service starts and table exists
- **THEN** log confirms table schema is valid or warns if schema differs from expected

### Requirement: Transaction management

The system SHALL use transactions for log insertions to ensure consistency.

#### Scenario: Successful transaction

- **WHEN** log entry is inserted
- **THEN** transaction commits and operation is confirmed

#### Scenario: Failed transaction

- **WHEN** log insertion fails
- **THEN** transaction rolls back and error is logged
