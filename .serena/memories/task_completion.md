# AWS Connectivity Test - Task Completion Checklist

## Before Considering a Task Complete

### 1. Code Quality
- [ ] Code follows the project's style (Black, isort)
- [ ] All functions have type hints
- [ ] Docstrings added for new code
- [ ] No flake8 warnings

### 2. Testing
- [ ] Tests written for new functionality
- [ ] All existing tests pass
- [ ] Tests use pytest-asyncio for async code

### 3. Run Quality Checks
```bash
# Format code
./scripts/local-dev.sh format

# Run linters
./scripts/local-dev.sh lint

# Run tests
./scripts/local-dev.sh test
```

Or manually:
```bash
black src/ tests/
isort src/ tests/
flake8 src/ tests/
mypy src/
pytest tests/
```

### 4. Documentation
- [ ] README updated if needed
- [ ] Configuration documented if new env vars added
- [ ] Docstrings added for public APIs

### 5. Git
- [ ] Changes are on a feature branch
- [ ] Commits are atomic and well-described
- [ ] No secrets or credentials committed

## Quick Verification Command
```bash
./scripts/local-dev.sh format && ./scripts/local-dev.sh lint && ./scripts/local-dev.sh test
```
