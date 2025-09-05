import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from grpc import aio as grpc_aio
from grpc_reflection.v1alpha import reflection
from redis.asyncio import Redis

from config import get_settings

# Generated protobuf files
from payment.v1 import payment_pb2, payment_pb2_grpc
from payment_handler import PaymentServiceHandler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("payment-service")

class EndpointFilter(logging.Filter):
    """Filter out noisy health check access logs."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - logging filter
        return "GET /health" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(EndpointFilter())


settings = get_settings()


async def serve_grpc(
    sessionmaker: async_sessionmaker,
    redis: Redis | None,
    bind: str = "0.0.0.0:50051",
    started_event: asyncio.Event | None = None,
) -> None:
    server = grpc_aio.server(maximum_concurrent_rpcs=100)
    payment_pb2_grpc.add_PaymentServiceServicer_to_server(
        PaymentServiceHandler(sessionmaker, redis), server
    )
    service_names = (
        payment_pb2.DESCRIPTOR.services_by_name["PaymentService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)
    server.add_insecure_port(bind)

    logger.info("Starting gRPC server on %s", bind)
    await server.start()
    if started_event is not None:
        started_event.set()
    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("Cancellation received; stopping gRPC server...")
        await server.stop(grace=5)
        raise
    finally:
        await server.stop(grace=0)


# FastAPI App
@asynccontextmanager
async def lifespan(app: FastAPI):
    engine: AsyncEngine = create_async_engine(settings.database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    # Ensure database is reachable before starting services
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))

    redis: Redis | None = None
    try:
        redis = Redis.from_url(
            settings.redis_url, encoding="utf-8", decode_responses=True
        )
        await redis.ping()
    except Exception as exc:  # pragma: no cover - startup warning
        logger.warning("Redis unavailable: %s", exc)
        redis = None

    started_event = asyncio.Event()
    grpc_task = asyncio.create_task(
        serve_grpc(sessionmaker, redis, started_event=started_event)
    )
    await started_event.wait()
    try:
        yield
    finally:
        grpc_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await grpc_task
        await engine.dispose()
        if redis is not None:
            await redis.close()

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
    return {"message": "Payment Service API", "grpc_port": settings.APP_GRPC_PORT}

if __name__ == "__main__":
    # Run FastAPI server
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.APP_REST_PORT,
        reload=True,
        log_level="info"
    )
