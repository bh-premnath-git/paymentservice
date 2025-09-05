# Payment Service

An experimental payment microservice showcasing a gRPC back end with a
REST/GraphQL gateway. It uses FastAPI for HTTP handling, SQLAlchemy with
PostgreSQL for persistence and optional Redis caching. A requestor mock service
demonstrates how other systems can consume the gRPC API through REST or
GraphQL.

## Project Layout

```
.
├── app/                     # Application source
│   ├── Dockerfile           # Runtime image for payment-service
│   ├── config.py            # Pydantic settings loaded from `.env`
│   ├── main.py              # FastAPI app and gRPC server startup
│   ├── models.py            # SQLAlchemy models (Payment table)
│   ├── payment_handler.py   # gRPC `PaymentService` implementation
│   ├── requirements.txt     # Python dependencies
│   └── adapters/            # Integrations with external payment processors
│       ├── base.py          # Adapter interface
│       ├── stripe/          # Stripe payment adapter
│       └── custom/          # Example custom payment adapter
├── payment/                 # Generated protobuf packages
├── protos/                  # Source `.proto` definitions
│   └── payment/v1/payment.proto
├── sandbox/                 # Example clients and mock services
│   └── requestor_mock/
│       ├── Dockerfile       # Image exposing REST & GraphQL
│       └── main.py
├── scripts/
│   └── init-db.sql          # Database initialisation script
├── tests/                   # Pytest suite
├── docker-compose.yml       # Development stack
├── .env                     # Environment variables consumed at runtime
├── Makefile                 # Common development commands
└── generate_protos.sh       # Helper to regenerate gRPC stubs
```

## Architecture and Implementation

The application entry point is `app/main.py`, which starts a FastAPI server for
health endpoints and a gRPC server implementing `PaymentService`. Business logic
lives in `app/payment_handler.py` and persists data using the SQLAlchemy models
from `app/models.py`. PostgreSQL provides durable storage, while Redis is used
as an optional caching layer.

## Payment Processor Adapters

To support multiple payment providers the service follows an adapter pattern.
Adapters live under `app/adapters/` and implement the
[`PaymentAdapter`](app/adapters/base.py) interface. Each adapter translates
between the internal payment model and the external processor's API.

### Stripe Adapter

[`app/adapters/stripe`](app/adapters/stripe/__init__.py) contains a minimal
adapter for Stripe. The class is asynchronous and returns mock responses so the
rest of the application can be developed without contacting Stripe. Replace the
stubbed methods with calls to the official `stripe` Python package when ready to
integrate with the real API.

```python
from adapters.stripe import StripeAdapter
adapter = StripeAdapter(api_key="sk_test_...", webhook_secret="whsec_...")
await adapter.create_payment(10, "USD")
```

### Stripe Webhooks

The FastAPI app exposes a `POST /webhooks/stripe` endpoint for receiving
events from the Stripe CLI. Start a local listener with:

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
```

Incoming payloads are validated using `STRIPE_WEBHOOK_SECRET` and the handler
responds with `{ "received": true }`. Extend the logic in
[`app/main.py`](app/main.py) to reconcile events with your system.

### Custom Adapter

[`app/adapters/custom`](app/adapters/custom/__init__.py) demonstrates how to
implement an in-house processor. It follows the same interface and can be used
as a template for future adapters.

### Adding New Adapters

1. Create a new subdirectory under `app/adapters/`.
2. Implement a class deriving from `PaymentAdapter`.
3. Provide asynchronous methods for creating, capturing, refunding and cancelling
   payments.
4. Wire the adapter into your application components as needed.

## gRPC API

The service defines a single gRPC API in
[`protos/payment/v1/payment.proto`](protos/payment/v1/payment.proto). The
`PaymentService` includes five RPCs:

- `CreatePayment` – store a new payment
- `GetPayment` – fetch a payment by ID
- `ListPayments` – retrieve all payments
- `ProcessPayment` – update status (capture, refund, cancel)
- `HealthCheck` – simple liveness probe

Generated Python code lives under `payment/v1/` and is used by the server and
clients.

## REST and GraphQL Gateways

The core service only exposes a small FastAPI layer with `/health` and root
information, but the sandbox `requestor_mock` container demonstrates how to wrap
the gRPC API:

- **REST**
  - `POST /api/payments` – create a payment
  - `GET /api/payments` – list payments
  - `GET /api/payments/{payment_id}` – retrieve payment details
- **GraphQL**
  - Query `payment(payment_id: ID!)` – fetch a payment
  - Query `payments` – list payments
  - Mutation `create_payment(payload: PaymentInput!)` – create a payment

These endpoints internally call the gRPC `PaymentService` using the generated
stubs. The mock can run alongside the service via `docker-compose`.

## Persistence and Caching

`app/main.py` configures an async SQLAlchemy engine against the `DATABASE_URL`
and sets up an optional Redis connection via `REDIS_URL`. The
`PaymentServiceHandler` writes `Payment` objects to PostgreSQL and caches recent
lookups in Redis for five minutes. A startup script
[`scripts/init-db.sql`](scripts/init-db.sql) creates the required `payments`
table when the database container initialises.

## Environment Variables

`.env` stores development defaults used by the service and docker-compose. Key
variables include database connection details, Redis URL, ports and feature
flags. Stripe integrations rely on `STRIPE_SECRET_KEY` and
`STRIPE_WEBHOOK_SECRET`. `app/config.py` loads these settings via
`pydantic-settings`.

## Docker and Docker Compose

The project ships with a `docker-compose.yml` file that defines the full
runtime stack:

- **payment-service** – main gRPC/HTTP server built from `app/Dockerfile`.
- **requestor-mock** – optional REST/GraphQL gateway used for examples.
- **postgres** – PostgreSQL 13 with an init script creating the `payments`
  table.
- **redis** – cache backend used by the handler for fast reads.
- **grpcui** – web-based gRPC client (enabled via the `tools` profile).

### Building Images

```bash
make build           # or: docker-compose build --no-cache
```

### Starting the Stack

```bash
docker-compose --profile tools up -d --build
```

The command above launches all services including the optional grpcui. Omit the
`--profile tools` flag to start only the core dependencies. Logs for all
containers can be tailed with `make logs` and the stack can be stopped with
`make down`.

### Running the Service Alone

To build and run only the payment-service container:

```bash
docker build -t payment-service app/
docker run --env-file .env -p 8000:8000 -p 50051:50051 payment-service
```

## Building and Running Locally

Proto stubs are generated with `generate_protos.sh`. The provided `Makefile`
wraps common tasks:

- `make protos` – regenerate protobuf code
- `make build` / `make up` / `make down` – manage containers
- `make test` – run the pytest suite inside a container

## Tests

The `tests/` directory contains unit tests that verify behaviour such as
metadata persistence, server reflection and metadata propagation through the
REST and GraphQL gateways.

