import logging
from datetime import datetime
import uuid

import grpc
from payment.v1 import payment_pb2, payment_pb2_grpc

logger = logging.getLogger(__name__)

class PaymentServiceHandler(payment_pb2_grpc.PaymentServiceServicer):
    def __init__(self):
        # In-memory storage for demo
        self.payments = {}
        logger.info("PaymentServiceHandler initialized")

    async def CreatePayment(self, request, context):
        """Create a new payment."""
        try:
            payment_id = str(uuid.uuid4())
            created_at = datetime.now().isoformat()
            
            # Store payment data
            payment_data = {
                "payment_id": payment_id,
                "amount": request.amount,
                "currency": request.currency,
                "customer_id": request.customer_id,
                "payment_method": request.payment_method,
                "metadata": dict(request.metadata),
                "status": "created",
                "created_at": created_at
            }
            
            self.payments[payment_id] = payment_data
            
            logger.info(f"Created payment: {payment_id}")
            
            return payment_pb2.CreatePaymentResponse(
                payment_id=payment_id,
                status="created",
                created_at=created_at
            )
            
        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to create payment: {str(e)}")
            return payment_pb2.CreatePaymentResponse()

    async def GetPayment(self, request, context):
        """Get payment by ID."""
        try:
            payment_id = request.payment_id
            
            if payment_id not in self.payments:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Payment not found: {payment_id}")
                return payment_pb2.GetPaymentResponse()
            
            payment = self.payments[payment_id]
            
            return payment_pb2.GetPaymentResponse(
                payment_id=payment["payment_id"],
                amount=payment["amount"],
                currency=payment["currency"],
                status=payment["status"],
                created_at=payment["created_at"]
            )
            
        except Exception as e:
            logger.error(f"Error getting payment: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to get payment: {str(e)}")
            return payment_pb2.GetPaymentResponse()

    async def ProcessPayment(self, request, context):
        """Process payment action."""
        try:
            payment_id = request.payment_id
            action = request.action
            
            if payment_id not in self.payments:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Payment not found: {payment_id}")
                return payment_pb2.ProcessPaymentResponse()
            
            # Update payment status based on action
            status_map = {
                "capture": "captured",
                "refund": "refunded", 
                "cancel": "cancelled"
            }
            
            new_status = status_map.get(action, "processed")
            processed_at = datetime.now().isoformat()
            
            self.payments[payment_id]["status"] = new_status
            self.payments[payment_id]["processed_at"] = processed_at
            
            logger.info(f"Processed payment {payment_id}: {action} -> {new_status}")
            
            return payment_pb2.ProcessPaymentResponse(
                payment_id=payment_id,
                status=new_status,
                processed_at=processed_at
            )
            
        except Exception as e:
            logger.error(f"Error processing payment: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to process payment: {str(e)}")
            return payment_pb2.ProcessPaymentResponse()

    async def HealthCheck(self, request, context):
        """Health check endpoint."""
        return payment_pb2.HealthCheckResponse(
            status="healthy",
            timestamp=datetime.now().isoformat()
        )