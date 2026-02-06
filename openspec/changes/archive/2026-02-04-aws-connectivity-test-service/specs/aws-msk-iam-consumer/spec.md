## ADDED Requirements

### Requirement: AWS MSK IAM authentication

The system SHALL authenticate to AWS MSK using IAM credentials via the `aws-msk-iam-sasl-signer-python` library with SASL_SSL security protocol.

#### Scenario: Successful IAM authentication

- **WHEN** the service starts and IAM credentials are available via IRSA
- **THEN** the consumer successfully authenticates to MSK and establishes connection

#### Scenario: Missing IAM credentials

- **WHEN** the service starts without IAM credentials
- **THEN** authentication fails with clear error message logged to stdout

### Requirement: Consumer group management

The system SHALL create and manage a Kafka consumer group with a configurable group ID.

#### Scenario: New consumer group

- **WHEN** the consumer starts with a group ID that doesn't exist
- **THEN** Kafka creates the consumer group and assigns partitions

#### Scenario: Existing consumer group

- **WHEN** the consumer starts with an existing group ID
- **THEN** the consumer joins the group and participates in rebalancing

### Requirement: Topic subscription

The system SHALL subscribe to one or more Kafka topics specified via the KAFKA_TOPICS environment variable (comma-separated).

#### Scenario: Single topic subscription

- **WHEN** KAFKA_TOPICS contains a single topic name
- **THEN** the consumer subscribes to that topic only

#### Scenario: Multiple topic subscription

- **WHEN** KAFKA_TOPICS contains multiple comma-separated topic names
- **THEN** the consumer subscribes to all specified topics

### Requirement: Message consumption

The system SHALL continuously consume messages from subscribed topics and pass them to the message handler.

#### Scenario: Message available

- **WHEN** a message is available on a subscribed topic
- **THEN** the consumer fetches the message and invokes the handler with topic, partition, offset, key, and value

#### Scenario: No messages available

- **WHEN** no messages are available
- **THEN** the consumer polls with timeout and logs periodic heartbeat

### Requirement: Graceful shutdown

The system SHALL handle SIGTERM signal by closing the consumer, committing offsets, and leaving the consumer group cleanly.

#### Scenario: SIGTERM received

- **WHEN** Kubernetes sends SIGTERM to the pod
- **THEN** consumer commits current offsets, closes connections, and exits within shutdown timeout

### Requirement: Bootstrap servers configuration

The system SHALL use bootstrap servers specified in the KAFKA_BOOTSTRAP_SERVERS environment variable.

#### Scenario: Valid bootstrap servers

- **WHEN** KAFKA_BOOTSTRAP_SERVERS contains valid MSK broker addresses
- **THEN** consumer connects successfully

#### Scenario: Invalid bootstrap servers

- **WHEN** KAFKA_BOOTSTRAP_SERVERS contains invalid addresses
- **THEN** connection fails with clear error logged

### Requirement: Offset management

The system SHALL use manual offset commit (auto_commit disabled) to ensure message processing before committing.

#### Scenario: Message processed successfully

- **WHEN** message handler completes without error
- **THEN** consumer commits the offset for that message

#### Scenario: Message processing fails

- **WHEN** message handler raises an exception
- **THEN** offset is not committed and message will be reprocessed

### Requirement: Verbose connection logging

The system SHALL log all connection attempts, authentication steps, and consumer state changes to stdout.

#### Scenario: Consumer initialization

- **WHEN** consumer starts
- **THEN** logs include: bootstrap servers, topics, consumer group, auth mechanism, connection status

#### Scenario: Partition assignment

- **WHEN** consumer receives partition assignment
- **THEN** logs include: assigned partitions, current offsets, consumer group state
