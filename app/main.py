import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from grpc import aio as grpc_aio

# Generated protobuf files
from payment.v1 import payment_pb2_grpc
from payment_handler import PaymentServiceHandler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("payment-service")

class EndpointFilter(logging.Filter):
    """Filter out noisy health check access logs."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - logging filter
        return "GET /health" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(EndpointFilter())


# gRPC Server
async def serve_grpc(bind: str = "[::]:50051") -> None:
    server = grpc_aio.server(maximum_concurrent_rpcs=100)
    payment_pb2_grpc.add_PaymentServiceServicer_to_server(PaymentServiceHandler(), server)
    server.add_insecure_port(bind)

    logger.info("Starting gRPC server on %s", bind)
    await server.start()
    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("Cancellation received; stopping gRPC server...")
        await server.stop(grace=5)
        raise
    finally:
        # Ensure stopped even if termination returns without cancellation
        await server.stop(grace=0)

# FastAPI App
@asynccontextmanager
async def lifespan(app: FastAPI):
    grpc_task = asyncio.create_task(serve_grpc())
    try:
        yield
    finally:
        grpc_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await grpc_task

app = FastAPI(
    title="Payment Service",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "payment-service"}

@app.get("/")
async def root():
    return {"message": "Payment Service API", "grpc_port": 50051}

if __name__ == "__main__":
    # Run FastAPI server
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
