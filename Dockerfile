FROM python:3.13-slim AS builder

WORKDIR /build

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
# Generate a lockfile-based install into /install prefix
RUN uv export --frozen --no-dev -o requirements.txt && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# ---------------------------------------------------------------------------
FROM python:3.13-slim

# curl for healthcheck + gosu for privilege drop in entrypoint
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl gosu && \
    rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=app:app app/ app/

# Data directory
RUN mkdir -p /app/data && chown app:app /app/data
ENV DATA_DIR=/app/data

# Entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/latest-date || exit 1

# Run as root so entrypoint can chown, then drops to app
ENTRYPOINT ["/entrypoint.sh"]
