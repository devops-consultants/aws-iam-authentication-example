## ADDED Requirements

### Requirement: OpenAI API authentication

The system SHALL authenticate to OpenAI API using an API key provided via the OPENAI_API_KEY environment variable.

#### Scenario: Valid API key

- **WHEN** OPENAI_API_KEY contains a valid API key
- **THEN** client successfully authenticates and can make requests

#### Scenario: Invalid API key

- **WHEN** OPENAI_API_KEY is missing or invalid
- **THEN** authentication fails with clear error message logged

### Requirement: Configurable embedding model

The system SHALL use the embedding model specified in the OPENAI_EMBEDDING_MODEL environment variable.

#### Scenario: Model specified

- **WHEN** OPENAI_EMBEDDING_MODEL contains a valid model name (e.g., "text-embedding-3-small")
- **THEN** client uses that model for all embedding requests

#### Scenario: Model not specified

- **WHEN** OPENAI_EMBEDDING_MODEL is not set
- **THEN** client defaults to "text-embedding-3-small"

### Requirement: Text embedding generation

The system SHALL generate vector embeddings from text content using the configured OpenAI model.

#### Scenario: Generate embedding from message text

- **WHEN** provided with Kafka message text content
- **THEN** client returns a vector embedding with dimensions matching the model's output

#### Scenario: Empty text content

- **WHEN** provided with empty or whitespace-only text
- **THEN** client logs warning and skips embedding generation

### Requirement: Async API calls

The system SHALL use the async OpenAI client to avoid blocking during embedding generation.

#### Scenario: Concurrent embedding requests

- **WHEN** multiple messages are being processed
- **THEN** embedding requests execute concurrently without blocking

### Requirement: Error handling and logging

The system SHALL log all API requests, responses, and errors with sufficient detail for debugging.

#### Scenario: Successful embedding generation

- **WHEN** embedding is generated successfully
- **THEN** log includes: input text length, model used, embedding dimensions, API latency

#### Scenario: API rate limit

- **WHEN** OpenAI API returns rate limit error
- **THEN** log includes clear rate limit message and does not retry

#### Scenario: API timeout

- **WHEN** OpenAI API request times out
- **THEN** log includes timeout error and request details

### Requirement: Embedding metadata capture

The system SHALL capture metadata about generated embeddings for logging and storage.

#### Scenario: Embedding metadata

- **WHEN** embedding is generated
- **THEN** system captures: model name, dimensions, input text length, timestamp

### Requirement: Client initialization logging

The system SHALL log OpenAI client initialization with configuration details.

#### Scenario: Client startup

- **WHEN** service starts
- **THEN** log includes: API key presence (masked), model name, client version
