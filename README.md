# Payment Service

This repository provides a gRPC-based payment service and a sandbox requestor mock used for local development and testing.

## Architecture and Communication

- **Protos** live in `protos/payment/v1/payment.proto` and are compiled into Python modules under `payment/v1`.
- `generate_protos.sh` (invoked via `make protos`) uses `grpcio-tools` in an isolated virtual environment to generate `*_pb2.py` and `*_pb2_grpc.py` files and ensures `__init__.py` files exist.
- The **app** in `app/` runs both a FastAPI HTTP server (port 8000) and a gRPC server (port 50051) that implements `CreatePayment`, `GetPayment`, `ProcessPayment`, and `HealthCheck` using the generated protobuf code.
- The sandbox **requestor mock** in `sandbox/requestor_mock/` is a FastAPI service that exposes REST endpoints and forwards requests to the payment service via gRPC. It reuses the same generated protobuf modules and connects to the gRPC endpoint `payment-service:50051`.

## Docker Setup

The project uses `docker-compose.yml` to orchestrate services:

- **payment-service** – built from `app/Dockerfile`, exposes ports 8000 (HTTP) and 50051 (gRPC), and depends on Postgres.
- **requestor-mock** – built from `sandbox/requestor_mock/Dockerfile`, exposes port 8001 and depends on payment-service.
- **postgres** – Postgres database initialized from `scripts/init-db.sql` and exposed on port 5432.
- **redis** – Redis instance on port 6379.
- **grpcui** – optional tool for exploring the gRPC API on port 8080 (enabled with profile `tools`).

All services share the `payment-network` Docker network and have basic health checks defined.

## Shell / Makefile Commands

The `Makefile` wraps common commands:

- `make protos` – generate gRPC code from `.proto` files.
- `make build` – build Docker images (runs `make protos` first).
- `make up` – start all services in the background.
- `make down` – stop services.
- `make logs` – follow logs for all containers.
- `make test` – run the pytest suite inside the `payment-service` container.
- `make clean` – remove generated protobuf files and Docker artifacts.

These commands rely on `docker-compose` and a `.env` file for configuration.

## Usage

1. Generate proto files:
   ```bash
   make protos
   ```
2. Build and start services:
   ```bash
   make up
   ```
3. The payment service is available at <http://localhost:8000> and gRPC on port `50051`.
4. The requestor mock exposes REST endpoints at <http://localhost:8001/api/payments>.

## Testing

Run the test suite through Docker:

```bash
make test
```

This command builds images if necessary, starts dependencies, and executes `pytest` inside the payment-service container.

