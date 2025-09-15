FROM python:3.13.7-slim as base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    gnupg \
    && rm -rf /var/lib/apt/lists/* \
    && curl -s https://packages.stripe.dev/api/security/keypair/stripe-cli-gpg/public | gpg --dearmor | tee /usr/share/keyrings/stripe.gpg >/dev/null \
    && echo "deb [signed-by=/usr/share/keyrings/stripe.gpg] https://packages.stripe.dev/stripe-cli-debian-local stable main" | tee -a /etc/apt/sources.list.d/stripe.list >/dev/null \
    && apt-get update \
    && apt-get install -y stripe

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
