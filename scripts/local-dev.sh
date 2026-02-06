#!/bin/bash
# =============================================================================
# AWS Connectivity Test - Local Development Helper Script
# =============================================================================
# This script provides convenient commands for local development.
# Usage: ./scripts/local-dev.sh <command>
# =============================================================================

set -e

# Color codes for output formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Print colored message
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Print help message
print_help() {
    echo "AWS Connectivity Test - Local Development Helper"
    echo ""
    echo "Usage: ./scripts/local-dev.sh <command>"
    echo ""
    echo "Commands:"
    echo "  setup       Set up the development environment (create venv, install deps)"
    echo "  start       Start the docker-compose stack"
    echo "  stop        Stop the docker-compose stack"
    echo "  restart     Restart the docker-compose stack"
    echo "  logs        Show application logs"
    echo "  logs-all    Show logs from all services"
    echo "  test        Run the test suite"
    echo "  lint        Run linters (black, flake8, mypy, isort)"
    echo "  format      Format code with black and isort"
    echo "  build       Build the Docker image"
    echo "  shell       Open a shell in the application container"
    echo "  psql        Connect to PostgreSQL database"
    echo "  kafka-topic Create a test Kafka topic"
    echo "  kafka-send  Send a test message to Kafka"
    echo "  clean       Clean up the environment (remove containers, volumes)"
    echo "  help        Show this help message"
}

# Set up development environment
setup() {
    print_message "$GREEN" "Setting up development environment..."

    cd "$PROJECT_DIR"

    # Create virtual environment if it doesn't exist
    if [ ! -d ".venv" ]; then
        print_message "$YELLOW" "Creating virtual environment..."
        python3.11 -m venv .venv
    fi

    # Activate virtual environment
    source .venv/bin/activate

    # Install dependencies
    print_message "$YELLOW" "Installing dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt

    # Create .env from example if it doesn't exist
    if [ ! -f ".env" ]; then
        print_message "$YELLOW" "Creating .env file from .env.example..."
        cp .env.example .env
    fi

    print_message "$GREEN" "Development environment setup complete!"
    print_message "$YELLOW" "Activate the virtual environment with: source .venv/bin/activate"
}

# Start docker-compose stack
start() {
    print_message "$GREEN" "Starting docker-compose stack..."
    cd "$PROJECT_DIR"
    docker-compose up -d
    print_message "$GREEN" "Stack started! Use 'logs' to view application logs."
}

# Stop docker-compose stack
stop() {
    print_message "$YELLOW" "Stopping docker-compose stack..."
    cd "$PROJECT_DIR"
    docker-compose down
    print_message "$GREEN" "Stack stopped."
}

# Restart docker-compose stack
restart() {
    stop
    start
}

# Show application logs
logs() {
    cd "$PROJECT_DIR"
    docker-compose logs -f connectivity-test
}

# Show all logs
logs_all() {
    cd "$PROJECT_DIR"
    docker-compose logs -f
}

# Run tests
test() {
    print_message "$GREEN" "Running tests..."
    cd "$PROJECT_DIR"

    if [ -d ".venv" ]; then
        source .venv/bin/activate
    fi

    pytest tests/ "$@"
}

# Run linters
lint() {
    print_message "$GREEN" "Running linters..."
    cd "$PROJECT_DIR"

    if [ -d ".venv" ]; then
        source .venv/bin/activate
    fi

    print_message "$YELLOW" "Running black check..."
    black --check src/ tests/

    print_message "$YELLOW" "Running isort check..."
    isort --check-only src/ tests/

    print_message "$YELLOW" "Running flake8..."
    flake8 src/ tests/

    print_message "$YELLOW" "Running mypy..."
    mypy src/

    print_message "$GREEN" "All linters passed!"
}

# Format code
format() {
    print_message "$GREEN" "Formatting code..."
    cd "$PROJECT_DIR"

    if [ -d ".venv" ]; then
        source .venv/bin/activate
    fi

    print_message "$YELLOW" "Running black..."
    black src/ tests/

    print_message "$YELLOW" "Running isort..."
    isort src/ tests/

    print_message "$GREEN" "Code formatting complete!"
}

# Build Docker image
build() {
    print_message "$GREEN" "Building Docker image..."
    cd "$PROJECT_DIR"
    docker build -t aws-connectivity-test:latest .
    print_message "$GREEN" "Image built: aws-connectivity-test:latest"
}

# Open shell in container
shell() {
    cd "$PROJECT_DIR"
    docker-compose exec connectivity-test /bin/bash
}

# Connect to PostgreSQL
psql() {
    cd "$PROJECT_DIR"
    docker-compose exec postgres psql -U postgres -d connectivity_test
}

# Create test Kafka topic
kafka_topic() {
    local topic=${1:-test-topic}
    print_message "$GREEN" "Creating Kafka topic: $topic"
    cd "$PROJECT_DIR"
    docker-compose exec kafka kafka-topics --create \
        --topic "$topic" \
        --bootstrap-server localhost:9092 \
        --partitions 1 \
        --replication-factor 1 \
        --if-not-exists
    print_message "$GREEN" "Topic created: $topic"
}

# Send test message to Kafka
kafka_send() {
    local topic=${1:-test-topic}
    local message=${2:-"Hello from AWS Connectivity Test!"}
    print_message "$GREEN" "Sending message to topic: $topic"
    cd "$PROJECT_DIR"
    echo "$message" | docker-compose exec -T kafka kafka-console-producer \
        --topic "$topic" \
        --bootstrap-server localhost:9092
    print_message "$GREEN" "Message sent!"
}

# Clean up environment
clean() {
    print_message "$YELLOW" "Cleaning up environment..."
    cd "$PROJECT_DIR"

    print_message "$YELLOW" "Stopping and removing containers..."
    docker-compose down -v --remove-orphans

    print_message "$YELLOW" "Removing virtual environment..."
    rm -rf .venv

    print_message "$YELLOW" "Removing cache directories..."
    rm -rf __pycache__ .pytest_cache .mypy_cache htmlcov .coverage

    print_message "$GREEN" "Cleanup complete!"
}

# Main command dispatcher
case "$1" in
    setup)
        setup
        ;;
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    logs)
        logs
        ;;
    logs-all)
        logs_all
        ;;
    test)
        shift
        test "$@"
        ;;
    lint)
        lint
        ;;
    format)
        format
        ;;
    build)
        build
        ;;
    shell)
        shell
        ;;
    psql)
        psql
        ;;
    kafka-topic)
        kafka_topic "$2"
        ;;
    kafka-send)
        kafka_send "$2" "$3"
        ;;
    clean)
        clean
        ;;
    help|--help|-h|"")
        print_help
        ;;
    *)
        print_message "$RED" "Unknown command: $1"
        print_help
        exit 1
        ;;
esac
