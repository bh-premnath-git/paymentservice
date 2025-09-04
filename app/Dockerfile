FROM python:3.13.7-slim as base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://stripe-cli.github.io/install.sh | sh

# Copy requirements first for better caching (from app directory)
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Development stage
FROM base as development
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Copy source code first (from app directory only)
COPY app .

# Copy pre-generated proto files (from root level)
COPY payment ./payment

# Expose ports
EXPOSE 8000 50051

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start both FastAPI and gRPC servers
CMD ["python", "main.py"]
