# CLAUDE.md

## Code Style
- Python 3.11, strict mypy type hints required
- Black (88 chars), isort (black profile), flake8
- Google-style docstrings for all public APIs
- Pydantic Settings for configuration via env vars

## Architecture
- FastAPI async service testing AWS connectivity (MSK, RDS, OpenSearch, ElastiCache)
- IAM authentication via IRSA in Kubernetes
- All clients in `src/aws_connectivity_test/` follow async patterns

## Testing
- pytest with pytest-asyncio (`asyncio_mode = "auto"`)
- Tests in `tests/`, run with `pytest tests/ -v`
