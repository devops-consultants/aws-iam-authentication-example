# AWS Connectivity Test - Development Commands

## Helper Script (Preferred)
All development commands are available through `scripts/local-dev.sh`:

```bash
./scripts/local-dev.sh setup       # Set up development environment (venv, deps)
./scripts/local-dev.sh start       # Start docker-compose stack
./scripts/local-dev.sh stop        # Stop docker-compose stack
./scripts/local-dev.sh restart     # Restart docker-compose stack
./scripts/local-dev.sh logs        # Show application logs
./scripts/local-dev.sh logs-all    # Show all service logs
./scripts/local-dev.sh test        # Run test suite
./scripts/local-dev.sh lint        # Run all linters
./scripts/local-dev.sh format      # Format code
./scripts/local-dev.sh build       # Build Docker image
./scripts/local-dev.sh psql        # Connect to PostgreSQL
./scripts/local-dev.sh kafka-send  # Send test message
./scripts/local-dev.sh clean       # Clean up environment
```

## Direct Commands (when venv is active)

### Testing
```bash
pytest tests/                      # Run all tests
pytest tests/ -v                   # Verbose output
pytest tests/ -k "test_name"       # Run specific test
pytest tests/ --cov=src            # With coverage
```

### Linting
```bash
black --check src/ tests/          # Check formatting
black src/ tests/                  # Apply formatting
isort --check-only src/ tests/     # Check import order
isort src/ tests/                  # Fix import order
flake8 src/ tests/                 # Style checks
mypy src/                          # Type checking
```

### Docker
```bash
docker build -t aws-connectivity-test:latest .
docker-compose up -d
docker-compose down
docker-compose logs -f connectivity-test
```

## Virtual Environment
```bash
python3.11 -m venv .venv           # Create venv
source .venv/bin/activate          # Activate venv
pip install -r requirements.txt    # Install deps
```
