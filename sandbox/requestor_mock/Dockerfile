FROM python:3.13.7-slim as base

WORKDIR /app

# Install runtime dependencies only (no grpcio-tools needed at runtime)
RUN pip install fastapi uvicorn grpcio==1.74.0 protobuf==6.31.1 \
    strawberry-graphql[fastapi]

# Copy pre-generated proto files (from root level)
COPY payment ./payment

# Copy application files (from sandbox/requestor_mock)
COPY sandbox/requestor_mock .

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["python", "main.py"]
