# Stage 1: Builder - Install dependencies
FROM python:3.14-slim AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install system dependencies and uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /server

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-install-project --no-dev


# Stage 2: Runtime - Minimal production image
FROM python:3.14-slim

# Build argument for Django settings module
ARG DJANGO_SETTINGS_MODULE=core.settings.development

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/server/.venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE}

# Install runtime dependencies only
RUN apt-get update  \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /server

# Copy virtual environment from builder
COPY --from=builder /server/.venv /server/.venv

# Copy application code
COPY . .

# Convert line endings and make scripts executable
RUN sed -i 's/\r$//' /server/assets/scripts/*.sh && \
    chmod +x /server/assets/scripts/*.sh

# Expose port
EXPOSE 8000

# Set default command
CMD ["./assets/scripts/server.sh"]