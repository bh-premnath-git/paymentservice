import asyncio
import logging
from contextlib import asynccontextmanager

import grpc
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Generated protobuf files  
from payment.v1 import payment_pb2, payment_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PaymentRequest(BaseModel):
    amount: str
    currency: str = "USD"
    customer_id: str
    payment_method: str = "card"

class PaymentGRPCClient:
    def __init__(self, target: str = "payment-service:50051"):
        self.target = target
        self.channel = None
        self.stub = None
    
    async def connect(self):
        """Connect to payment service gRPC."""
        self.channel = grpc.aio.insecure_channel(self.target)
        self.stub = payment_pb2_grpc.PaymentServiceStub(self.channel)
        
        # Test connection
        try:
            response = await self.stub.HealthCheck(payment_pb2.HealthCheckRequest())
            logger.info(f"Connected to payment service: {response.status}")
        except Exception as e:
            logger.error(f"Failed to connect to payment service: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from payment service."""
        if self.channel:
            await self.channel.close()

    async def create_payment(self, payment_data: PaymentRequest):
        """Create payment via gRPC."""
        request = payment_pb2.CreatePaymentRequest(
            amount=payment_data.amount,
            currency=payment_data.currency,
            customer_id=payment_data.customer_id,
            payment_method=payment_data.payment_method
        )
        
        response = await self.stub.CreatePayment(request)
        return {
            "payment_id": response.payment_id,
            "status": response.status,
            "created_at": response.created_at
        }

    async def get_payment(self, payment_id: str):
        """Get payment via gRPC."""
        request = payment_pb2.GetPaymentRequest(payment_id=payment_id)
        response = await self.stub.GetPayment(request)
        return {
            "payment_id": response.payment_id,
            "amount": response.amount,
            "currency": response.currency,
            "status": response.status,
            "created_at": response.created_at
        }

# Global gRPC client
grpc_client = PaymentGRPCClient()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await grpc_client.connect()
    yield
    # Shutdown
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
        result = await grpc_client.create_payment(payment)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Failed to create payment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/payments/{payment_id}")
async def get_payment_rest(payment_id: str):
    """REST endpoint to get payment."""
    try:
        result = await grpc_client.get_payment(payment_id)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Failed to get payment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# GraphQL placeholder (basic)
@app.post("/graphql")
async def graphql_endpoint():
    """GraphQL endpoint placeholder."""
    return {"message": "GraphQL endpoint - implement with strawberry/graphene"}

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