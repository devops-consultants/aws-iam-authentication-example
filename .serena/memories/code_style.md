# AWS Connectivity Test - Code Style & Conventions

## Python Style

### Formatting
- **Line length**: 88 characters (Black default)
- **Formatter**: Black
- **Import sorting**: isort with Black profile
- **Target Python**: 3.11

### Type Hints
- **Required**: All function signatures must have type hints
- **mypy**: Strict mode enabled
  - `disallow_untyped_defs = true`
  - `disallow_incomplete_defs = true`
  - `check_untyped_defs = true`

### Docstrings
- **Style**: Google-style docstrings
- **Required for**: Classes, methods, and functions
- **Format**:
```python
def function_name(param: Type) -> ReturnType:
    """
    Brief description.

    Args:
        param: Description of parameter

    Returns:
        Description of return value

    Raises:
        ExceptionType: When this happens
    """
```

### Naming Conventions
- **Variables/functions**: snake_case
- **Classes**: PascalCase
- **Constants**: UPPER_SNAKE_CASE
- **Private**: Leading underscore (_private_var)

### Module Structure
- Section headers using comment blocks:
```python
# -------------------------------------------------------------------------
# Section Name
# -------------------------------------------------------------------------
# Description of the section
# -------------------------------------------------------------------------
```

### Pydantic Models
- Use `Field()` with descriptions for all settings
- Group related settings under section headers
- Use `@field_validator` for validation
- Use `@property` for computed values

### Async Patterns
- Use `async/await` consistently
- Use `asyncpg` for PostgreSQL
- Use `aiokafka` for Kafka
- Proper cleanup in finally blocks

### Configuration
- All configuration via environment variables
- Use `pydantic-settings` with `.env` file support
- Sensible defaults for local development
- Clear separation of IAM vs password auth modes

### Logging
- Use `structlog` for structured JSON logging
- Include context (service name, version)
- Log at appropriate levels (DEBUG, INFO, WARNING, ERROR)
