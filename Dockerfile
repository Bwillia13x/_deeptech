# Multi-stage build for smaller final image
FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml README.md ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -e .

# Runtime stage
FROM python:3.12-slim AS runtime

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r harvester && useradd -r -g harvester harvester

# Set working directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/harvest* /usr/local/bin/

# Copy application code
COPY --chown=harvester:harvester src/ ./src/
COPY --chown=harvester:harvester config/ ./config/

# Create directories for data and logs
RUN mkdir -p /app/var /app/data /app/logs && \
    chown -R harvester:harvester /app

# Switch to non-root user
USER harvester

# Set environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import httpx; response = httpx.get('http://localhost:8000/health', timeout=2); exit(0 if response.status_code == 200 else 1)"

# Expose API port
EXPOSE 8000

# Default command runs the API
CMD ["harvest-api", "--host", "0.0.0.0", "--port", "8000"]
