import os
import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict

import grpc
import uvicorn
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
import strawberry
from strawberry.scalars import JSON
from strawberry.exceptions import GraphQLError
from strawberry.fastapi import GraphQLRouter

from payment.v1 import payment_pb2, payment_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("requestor-mock")

class EndpointFilter(logging.Filter):
    """Filter out noisy health check access logs."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - logging filter
        return "GET /health" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

class PaymentRequest(BaseModel):
    amount: str
    currency: str = "USD"
    customer_id: str
    payment_method: str = "card"
    metadata: dict[str, str] = Field(default_factory=dict)

def grpc_to_http_status(code: grpc.StatusCode) -> int:
    mapping = {
        grpc.StatusCode.INVALID_ARGUMENT: status.HTTP_400_BAD_REQUEST,
        grpc.StatusCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
        grpc.StatusCode.ALREADY_EXISTS: status.HTTP_409_CONFLICT,
        grpc.StatusCode.PERMISSION_DENIED: status.HTTP_403_FORBIDDEN,
        grpc.StatusCode.UNAUTHENTICATED: status.HTTP_401_UNAUTHORIZED,
        grpc.StatusCode.RESOURCE_EXHAUSTED: status.HTTP_429_TOO_MANY_REQUESTS,
        grpc.StatusCode.UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED: status.HTTP_504_GATEWAY_TIMEOUT,
    }
    return mapping.get(code, status.HTTP_500_INTERNAL_SERVER_ERROR)


class PaymentGRPCClient:
    def __init__(self, target: str | None = None):
        self.target = target or os.getenv("PAYMENT_GRPC_TARGET", "payment-service:50051")
        self.channel: grpc.aio.Channel | None = None
        self.stub: payment_pb2_grpc.PaymentServiceStub | None = None

    async def connect(self, retries: int = 5, delay: float = 1.0):
        self.channel = grpc.aio.insecure_channel(self.target)
        self.stub = payment_pb2_grpc.PaymentServiceStub(self.channel)

        for attempt in range(1, retries + 1):
            try:
                await self.stub.HealthCheck(payment_pb2.HealthCheckRequest())
                logger.info("Connected to payment service at %s", self.target)
                return
            except grpc.RpcError as e:
                logger.warning("Attempt %d failed: %s (%s)", attempt, e.details(), e.code().name)
            except Exception as e:
                logger.warning("Attempt %d failed: %r", attempt, e)

            if attempt == retries:
                raise
            await asyncio.sleep(delay)
            delay *= 2

    async def disconnect(self):
        if self.channel:
            await self.channel.close()

    async def create_payment(self, payload: PaymentRequest):
        req = payment_pb2.CreatePaymentRequest(
            amount=payload.amount,
            currency=payload.currency,
            customer_id=payload.customer_id,
            payment_method=payload.payment_method,
            metadata=payload.metadata,
        )
        resp = await self.stub.CreatePayment(req)  # type: ignore[arg-type]
        return {
            "payment_id": resp.payment_id,
            "status": resp.status,
            "created_at": resp.created_at,
        }

    async def get_payment(self, payment_id: str):
        resp = await self.stub.GetPayment(payment_pb2.GetPaymentRequest(payment_id=payment_id))
        return {
            "payment_id": resp.payment_id,
            "amount": resp.amount,
            "currency": resp.currency,
            "status": resp.status,
            "created_at": resp.created_at,
        }

    async def list_payments(self):
        resp = await self.stub.ListPayments(payment_pb2.ListPaymentsRequest())
        return [
            {
                "payment_id": p.payment_id,
                "amount": p.amount,
                "currency": p.currency,
                "status": p.status,
                "created_at": p.created_at,
            }
            for p in resp.payments
        ]

# Global gRPC client
grpc_client = PaymentGRPCClient()


@strawberry.type
class Payment:
    payment_id: str
    amount: str
    currency: str
    status: str
    created_at: str


@strawberry.input
class PaymentInput:
    amount: str
    currency: str = "USD"
    customer_id: str
    payment_method: str = "card"
    metadata: JSON = strawberry.field(default_factory=dict)


@strawberry.type
class Query:
    @strawberry.field
    async def payment(self, payment_id: str) -> Payment:
        try:
            data = await grpc_client.get_payment(payment_id)
            return Payment(**data)
        except grpc.RpcError as e:
            raise GraphQLError(e.details() or e.code().name)

    @strawberry.field
    async def payments(self) -> list[Payment]:
        try:
            data = await grpc_client.list_payments()
            return [Payment(**p) for p in data]
        except grpc.RpcError as e:
            raise GraphQLError(e.details() or e.code().name)


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_payment(self, payload: PaymentInput) -> Payment:
        try:
            req = PaymentRequest(**asdict(payload))
            result = await grpc_client.create_payment(req)
            data = await grpc_client.get_payment(result["payment_id"])
            return Payment(**data)
        except grpc.RpcError as e:
            raise GraphQLError(e.details() or e.code().name)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await grpc_client.connect()
    try:
        yield
    finally:
        await grpc_client.disconnect()

app = FastAPI(
    title="Requestor Mock Service",
    version="1.0.0",
    lifespan=lifespan
)

# REST Endpoints
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "requestor-mock"}

@app.post("/api/payments")
async def create_payment_rest(payment: PaymentRequest):
    """REST endpoint to create payment."""
    try:
        return {"success": True, "data": await grpc_client.create_payment(payment)}
    except grpc.RpcError as e:
        raise HTTPException(status_code=grpc_to_http_status(e.code()), detail=e.details() or e.code().name)

@app.get("/api/payments")
async def list_payments_rest():
    """REST endpoint to list payments."""
    try:
        return {"success": True, "data": await grpc_client.list_payments()}
    except grpc.RpcError as e:
        raise HTTPException(status_code=grpc_to_http_status(e.code()), detail=e.details() or e.code().name)

@app.get("/api/payments/{payment_id}")
async def get_payment_rest(payment_id: str):
    """REST endpoint to get payment."""
    try:
        return {"success": True, "data": await grpc_client.get_payment(payment_id)}
    except grpc.RpcError as e:
        raise HTTPException(status_code=grpc_to_http_status(e.code()), detail=e.details() or e.code().name)

# GraphQL setup
schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_app = GraphQLRouter(schema, graphql_ide="graphiql")
app.include_router(graphql_app, prefix="/graphql")

@app.get("/")
async def root():
    return {
        "message": "Requestor Mock Service",
        "endpoints": {
            "rest": "/api/payments",
            "graphql": "/graphql"
        }
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )
