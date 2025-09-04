docker-compose --profile tools up -d --build

# Payment Service

This repository provides a gRPC-based payment service and a sandbox requestor mock used for local development and testing.

## Architecture and Communication

- **Protos** live in `protos/payment/v1/payment.proto` and are compiled into Python modules under `payment/v1`.
- `generate_protos.sh` (invoked via `make protos`) uses `grpcio-tools` in an isolated virtual environment to generate `*_pb2.py` and `*_pb2_grpc.py` files and ensures `__init__.py` files exist.
- The **app** in `app/` runs both a FastAPI HTTP server (port 8000) and a gRPC server (port 50051) that implements `CreatePayment`, `GetPayment`, `ProcessPayment`, and `HealthCheck` using the generated protobuf code.
- The sandbox **requestor mock** in `sandbox/requestor_mock/` is a FastAPI service that exposes REST and GraphQL APIs and forwards requests to the payment service via gRPC. It reuses the same generated protobuf modules and connects to the gRPC endpoint `payment-service:50051`.

## Docker Setup

The project uses `docker-compose.yml` to orchestrate services:

- **payment-service** – built from `app/Dockerfile`, exposes ports 8000 (HTTP) and 50051 (gRPC), and depends on Postgres.
- **requestor-mock** – built from `sandbox/requestor_mock/Dockerfile`, exposes port 8001 and depends on payment-service.
- **postgres** – Postgres database initialized from `scripts/init-db.sql` and exposed on port 5432.
- **redis** – Redis instance on port 6379.
- **grpcui** – optional tool for exploring the gRPC API on port 8080 (enabled with profile `tools`).

All services share the `payment-network` Docker network and have basic health checks defined.

### Service Overview

#### payment-service
- **Path:** `app/`
- **Ports:** 8000 (HTTP), 50051 (gRPC)
- **Purpose:** Hosts the main payment API. Implements FastAPI endpoints and the gRPC `PaymentService` with methods such as `CreatePayment`, `GetPayment`, `ProcessPayment`, and `HealthCheck`.
- **Dependencies:** Requires Postgres for persistence and optionally Redis for caching.
- **Health Check:** `GET /health`

#### requestor-mock
- **Path:** `sandbox/requestor_mock/`
- **Port:** 8001
- **Purpose:** Simulates an external requestor. Forwards requests to `payment-service` via gRPC and exposes both REST and GraphQL interfaces for testing.
- **Health Check:** `GET /health`

#### postgres
- **Image:** `postgres:13.22-alpine3.21`
- **Port:** 5432
- **Purpose:** Stores payment records. Initializes schema from `scripts/init-db.sql` and persists data in a Docker volume.

#### redis
- **Image:** `redis:alpine3.22`
- **Port:** 6379
- **Purpose:** Provides a Redis instance for caching or other ephemeral storage needs.

#### grpcui (optional)
- **Image:** `fullstorydev/grpcui:latest`
- **Port:** 8080
- **Purpose:** Web UI for manually invoking gRPC methods during development. Depends on `payment-service` being available on port 50051. If `payment-service` is not running or the gRPC server has not started yet, `grpcui` will show a connection-refused error.

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

4. The requestor mock exposes REST endpoints at <http://localhost:8001/api/payments> and a GraphQL API at <http://localhost:8001/graphql>.

## Inspecting the gRPC API

To browse and interact with the gRPC methods from your browser, start the optional `grpcui` container:

```bash
docker compose up grpcui
```

This launches a web UI at <http://localhost:8080/> that connects to the gRPC server. The `grpcui` service is run with the `-plaintext` flag to match the server's lack of TLS, and no additional authentication is required.

### Example: `CreatePayment`

1. Navigate to <http://localhost:8080/> and select `payment.v1.PaymentService`.
2. Choose the `CreatePayment` method and supply a request body such as:

```json
{
  "amount": "10.00",
  "currency": "USD",
  "customer_id": "cust123",
  "payment_method": "card"
}
```

3. Submit the request to view the response, which includes fields like `payment_id`, `status`, and `created_at`.


## API Reference

### REST Endpoints

| Method | Path | Description | Body |
| ------ | ---- | ----------- | ---- |
| `GET`  | `/health` | Service health check | _None_ |
| `POST` | `/api/payments` | Create a new payment | `amount` (string), `currency` (string, default `USD`), `customer_id` (string), `payment_method` (string, default `card`) |
| `GET`  | `/api/payments/{payment_id}` | Retrieve a payment by ID | _None_ |

Successful REST responses have the shape:

```json
{
  "success": true,
  "data": {
    "payment_id": "...",
    "amount": "...",
    "currency": "...",
    "status": "...",
    "created_at": "..."
  }
}
```

### GraphQL Operations

The GraphQL endpoint is available at `/graphql` with the interactive GraphiQL UI enabled.

#### Query

```graphql
query ($id: String!) {
  payment(paymentId: $id) {
    paymentId
    amount
    currency
    status
    createdAt
  }
}
```

#### Mutation

```graphql
mutation ($input: PaymentInput!) {
  createPayment(payload: $input) {
    paymentId
    amount
    currency
    status
    createdAt
  }
}
```

`PaymentInput` requires `amount`, `currency` (default `USD`), `customer_id`, and `payment_method` (default `card`). GraphQL `Payment` objects return `paymentId`, `amount`, `currency`, `status`, and `createdAt` fields.


## Testing

Run the test suite through Docker:

```bash
make test
```

This command builds images if necessary, starts dependencies, and executes `pytest` inside the payment-service container.

