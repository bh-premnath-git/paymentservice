import asyncio
import logging
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import grpc
from grpc import aio

# Generated protobuf files
from payment.v1 import payment_pb2_grpc
from payment_handler import PaymentServiceHandler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# gRPC Server
async def serve_grpc():
    server = aio.server(ThreadPoolExecutor(max_workers=10))
    
    # Add payment service handler
    payment_handler = PaymentServiceHandler()
    payment_pb2_grpc.add_PaymentServiceServicer_to_server(payment_handler, server)
    
    # Add insecure port
    listen_addr = '[::]:50051'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"Starting gRPC server on {listen_addr}")
    await server.start()
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down gRPC server...")
        await server.stop(5)

# FastAPI App
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start gRPC server in background
    grpc_task = asyncio.create_task(serve_grpc())
    yield
    # Cleanup
    grpc_task.cancel()
    try:
        await grpc_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="Payment Service",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_credentials=True,
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
