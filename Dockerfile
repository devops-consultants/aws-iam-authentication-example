# =============================================================================
# AWS Connectivity Test Service Dockerfile
# =============================================================================
# This Dockerfile builds a container for testing AWS service connectivity
# (MSK, RDS, OpenSearch) with IAM authentication in Kubernetes environments.
# =============================================================================

# Use Python 3.11 slim as base image for smaller footprint
FROM python:3.14-slim

# -----------------------------------------------------------------------------
# Environment Configuration
# -----------------------------------------------------------------------------
# PYTHONUNBUFFERED: Ensures Python output is sent straight to terminal
# PYTHONDONTWRITEBYTECODE: Prevents Python from writing .pyc files
# PIP_NO_CACHE_DIR: Disables pip cache to reduce image size
# PIP_DISABLE_PIP_VERSION_CHECK: Skips pip version check for faster builds
# -----------------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set work directory
WORKDIR /app

# -----------------------------------------------------------------------------
# Install UV Package Manager
# -----------------------------------------------------------------------------
# UV is a fast Python package installer that significantly speeds up builds
# We copy it from the official UV image to get the pre-built binary
# -----------------------------------------------------------------------------
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# -----------------------------------------------------------------------------
# Install System Dependencies
# -----------------------------------------------------------------------------
# These are required for building some Python packages:
# - gcc, g++: C/C++ compilers for native extensions
# - libpq-dev: PostgreSQL development headers for asyncpg
# - ca-certificates: SSL certificates for AWS API calls
# -----------------------------------------------------------------------------
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# Install Python Dependencies
# -----------------------------------------------------------------------------
# Copy requirements first for better Docker layer caching
# This means dependencies are only reinstalled when requirements.txt changes
# -----------------------------------------------------------------------------
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# -----------------------------------------------------------------------------
# Copy Application Code
# -----------------------------------------------------------------------------
# Copy the source code into the container
# The src/ directory contains the main application package
# -----------------------------------------------------------------------------
COPY src/ ./src/

# Copy configuration files
COPY pyproject.toml .

# -----------------------------------------------------------------------------
# Security Configuration
# -----------------------------------------------------------------------------
# Create a non-root user for running the application
# This is a security best practice to limit container privileges
# -----------------------------------------------------------------------------
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /app
USER appuser

# -----------------------------------------------------------------------------
# Python Path Configuration
# -----------------------------------------------------------------------------
# Set PYTHONPATH so Python can find our source packages
# -----------------------------------------------------------------------------
ENV PYTHONPATH=/app/src

# -----------------------------------------------------------------------------
# Expose Port
# -----------------------------------------------------------------------------
# The FastAPI application runs on port 8080 for health checks
# This port should match the service.port in the Helm values
# -----------------------------------------------------------------------------
EXPOSE 8080

# -----------------------------------------------------------------------------
# Run the Application
# -----------------------------------------------------------------------------
# Start the FastAPI application using uvicorn as the ASGI server
# The application module is aws_connectivity_test.main with the app instance
# Host 0.0.0.0 binds to all interfaces (required for Kubernetes)
# -----------------------------------------------------------------------------
CMD ["python", "-m", "uvicorn", "aws_connectivity_test.main:app", "--host", "0.0.0.0", "--port", "8080"]
