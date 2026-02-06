## ADDED Requirements

### Requirement: OpenSearch IAM authentication

The system SHALL authenticate to OpenSearch Serverless using AWS IAM credentials via SigV4 request signing.

#### Scenario: Successful IAM authentication

- **WHEN** service starts with valid IAM credentials from IRSA
- **THEN** OpenSearch client successfully authenticates and can perform operations

#### Scenario: Missing IAM credentials

- **WHEN** service starts without IAM credentials
- **THEN** authentication fails with clear error logged

### Requirement: Configurable endpoint and index

The system SHALL use the OpenSearch endpoint and index name specified via OPENSEARCH_ENDPOINT and OPENSEARCH_INDEX environment variables.

#### Scenario: Valid endpoint and index

- **WHEN** OPENSEARCH_ENDPOINT and OPENSEARCH_INDEX are provided
- **THEN** client connects to the specified endpoint and writes to the specified index

#### Scenario: Missing configuration

- **WHEN** OPENSEARCH_ENDPOINT or OPENSEARCH_INDEX are not set
- **THEN** service fails to start with clear error message

### Requirement: Vector embedding storage

The system SHALL write vector embeddings to OpenSearch with metadata.

#### Scenario: Store embedding with metadata

- **WHEN** provided with a vector embedding and metadata (timestamp, topic, message ID)
- **THEN** document is written to OpenSearch with vector field and metadata fields

#### Scenario: Document ID generation

- **WHEN** writing a document
- **THEN** system generates unique document ID from Kafka metadata (topic-partition-offset)

### Requirement: Index existence validation

The system SHALL verify the target index exists on startup and log the validation result.

#### Scenario: Index exists

- **WHEN** service starts and target index exists
- **THEN** log confirms index exists and is ready for writes

#### Scenario: Index does not exist

- **WHEN** service starts and target index does not exist
- **THEN** log warns that index does not exist but allows service to continue (index may be created externally)

### Requirement: Async write operations

The system SHALL use async OpenSearch client to avoid blocking during document writes.

#### Scenario: Concurrent writes

- **WHEN** multiple embeddings need to be written
- **THEN** writes execute concurrently without blocking

### Requirement: Write operation logging

The system SHALL log all write operations with sufficient detail for verification.

#### Scenario: Successful write

- **WHEN** document is written successfully
- **THEN** log includes: index name, document ID, vector dimensions, metadata, write latency

#### Scenario: Write failure

- **WHEN** write operation fails
- **THEN** log includes: error type, error message, document details, retry status

### Requirement: Connection initialization logging

The system SHALL log OpenSearch client initialization with configuration details.

#### Scenario: Client startup

- **WHEN** service starts
- **THEN** log includes: endpoint (masked if sensitive), index name, auth method, connection status

### Requirement: Vector field structure

The system SHALL write vectors in the expected field structure for OpenSearch vector search.

#### Scenario: Vector document structure

- **WHEN** writing an embedding
- **THEN** document includes: "vector" field with float array, "metadata" field with source info, "timestamp" field
