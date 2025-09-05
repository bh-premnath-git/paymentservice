# Payment Service

An experimental payment microservice showcasing a gRPC back end with a
REST/GraphQL gateway.  It uses FastAPI for HTTP handling, SQLAlchemy with
PostgreSQL for persistence and optional Redis caching.  A requestor mock
service demonstrates how other systems can consume the gRPC API through REST or
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
│   └── requirements.txt     # Python dependencies
|   |__ adapters/            # Adapters for external payment services
|   |__ |__ stripe/          # Stripe payment adapter
|   |__ |__ custom/          # Custom payment adapter
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

## gRPC API

The service defines a single gRPC API in
[`protos/payment/v1/payment.proto`](protos/payment/v1/payment.proto).  The
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
information, but the sandbox `requestor_mock` container demonstrates how to
wrap the gRPC API:

- **REST**
  - `POST /api/payments` – create a payment
  - `GET /api/payments` – list payments
  - `GET /api/payments/{payment_id}` – retrieve payment details
- **GraphQL**
  - Query `payment(payment_id: ID!)` – fetch a payment
  - Query `payments` – list payments
  - Mutation `create_payment(payload: PaymentInput!)` – create a payment

These endpoints internally call the gRPC `PaymentService` using the generated
stubs.  The mock can run alongside the service via `docker-compose`.

## Persistence and Caching

`app/main.py` configures an async SQLAlchemy engine against the `DATABASE_URL`
and sets up an optional Redis connection via `REDIS_URL`.  The
`PaymentServiceHandler` writes `Payment` objects to PostgreSQL and caches recent
lookups in Redis for five minutes.  A startup script
[`scripts/init-db.sql`](scripts/init-db.sql) creates the required `payments`
table when the database container initialises.

## Environment Variables

`.env` stores development defaults used by the service and docker-compose.  Key
variables include database connection details, Redis URL, ports and feature
flags.  `app/config.py` loads these settings via `pydantic-settings`.

## Building and Running

Proto stubs are generated with `generate_protos.sh`.  The provided `Makefile`
wraps common tasks:

- `make protos` – regenerate protobuf code
- `make build` / `make up` / `make down` – manage containers
- `make test` – run the pytest suite

The full stack (payment service, requestor mock, PostgreSQL, Redis and grpcui)
can be started with:

```bash
docker-compose --profile tools up -d --build
```

## Tests

The `tests/` directory contains unit tests that verify behaviour such as
metadata persistence, server reflection and metadata propagation through the
REST and GraphQL gateways.

start the service with tools profile:
 - docker-compose --profile tools up -d --build
