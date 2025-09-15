.PHONY: help protos clean build up down logs test

# Default target
help:
	@echo " International Money Transfer Payment Service"
	@echo ""
	@echo "Available commands:"
	@echo "  make protos    - Generate Python gRPC files from all .proto files"
	@echo "  make clean     - Clean generated proto files and Docker artifacts"
	@echo "  make build     - Build Docker containers"
	@echo "  make up        - Start all services"
	@echo "  make down      - Stop all services"
	@echo "  make logs      - Show logs from all services"
	@echo "  make restart   - Restart all services"
	@echo "  make test      - Run tests"
	@echo ""

# Generate protobuf files
protos:
	@echo " Generating proto files..."
	@if [ -f "./generate_protos.sh" ]; then \
		echo "Found generate_protos.sh, running with bash..."; \
		bash -c 'chmod +x generate_protos.sh && ./generate_protos.sh'; \
	else \
		echo "Error: generate_protos.sh not found in current directory"; \
		echo "Current directory: $$(pwd)"; \
		echo "Contents:"; \
		ls -la; \
		exit 1; \
	fi

# Clean generated files and Docker artifacts
clean:
	@echo " Cleaning generated files..."
	@find . -name "*_pb2.py" -type f -delete 2>/dev/null || true
	@find . -name "*_pb2_grpc.py" -type f -delete 2>/dev/null || true
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -type f -delete 2>/dev/null || true
	@echo " Cleaning Docker artifacts..."
	@docker-compose down --volumes --remove-orphans 2>/dev/null || true
	@docker system prune -f 2>/dev/null || true

# Build Docker containers
build: protos
	@echo "  Building Docker containers..."
	@docker-compose build --no-cache

# Start all services
up: protos
	@echo " Starting services..."
	@docker-compose up -d

# Stop all services
down:
	@echo " Stopping services..."
	@docker-compose down

# Show logs
logs:
	@echo " Service logs..."
	@docker-compose logs -f

# Restart services
restart: down up

# Development mode (with logs)
dev: protos
	@echo " Starting development mode..."
	@docker-compose up --build

# Run tests
test: protos
	@echo " Running tests..."
	@docker-compose run --rm payment-service python -m pytest

# Health check
health:
	@echo " Checking service health..."
	@curl -f http://localhost:8000/health || echo " Payment service unhealthy"
	@curl -f http://localhost:8001/health || echo " Requestor mock unhealthy"

# Install dependencies
install:
	@echo " Installing dependencies..."
	@pip install grpcio-tools
	@pip install -r app/requirements.txt