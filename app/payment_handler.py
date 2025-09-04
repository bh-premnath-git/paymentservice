import asyncio
import logging
from datetime import datetime, timezone
import uuid

import grpc
from payment.v1 import payment_pb2, payment_pb2_grpc

logger = logging.getLogger(__name__)

class PaymentServiceHandler(payment_pb2_grpc.PaymentServiceServicer):
    def __init__(self):
        self._payments: dict[str, dict] = {}
        self._lock = asyncio.Lock()
        logger.info("PaymentServiceHandler initialized")

    async def CreatePayment(self, request, context):
        """Create a new payment."""
        try:
            payment_id = str(uuid.uuid4())
            created_at = datetime.now(timezone.utc).isoformat()

            payment_data = {
                "payment_id": payment_id,
                "amount": request.amount,
                "currency": request.currency,
                "customer_id": request.customer_id,
                "payment_method": request.payment_method,
                "metadata": dict(getattr(request, "metadata", {})),
                "status": "created",
                "created_at": created_at,
            }

            async with self._lock:
                self._payments[payment_id] = payment_data

            logger.info("Created payment %s", payment_id)
            return payment_pb2.CreatePaymentResponse(
                payment_id=payment_id, status="created", created_at=created_at
            )

        except Exception as e:
            logger.exception("Error creating payment")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to create payment: {e}")
            return payment_pb2.CreatePaymentResponse()

    async def GetPayment(self, request, context):
        """Get payment by ID."""
        try:
            payment_id = request.payment_id
            async with self._lock:
                payment = self._payments.get(payment_id)

            if not payment:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Payment not found: {payment_id}")
                return payment_pb2.GetPaymentResponse()

            return payment_pb2.GetPaymentResponse(
                payment_id=payment["payment_id"],
                amount=payment["amount"],
                currency=payment["currency"],
                status=payment["status"],
                created_at=payment["created_at"],
            )

        except Exception as e:
            logger.exception("Error getting payment")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to get payment: {e}")
            return payment_pb2.GetPaymentResponse()

    async def ProcessPayment(self, request, context):
        """Process payment action."""
        try:
            payment_id = request.payment_id
            action = request.action

            status_map = {
                "capture": "captured",
                "refund": "refunded",
                "cancel": "cancelled",
            }
            new_status = status_map.get(action, "processed")
            processed_at = datetime.now(timezone.utc).isoformat()

            async with self._lock:
                payment = self._payments.get(payment_id)
                if not payment:
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    context.set_details(f"Payment not found: {payment_id}")
                    return payment_pb2.ProcessPaymentResponse()
                payment["status"] = new_status
                payment["processed_at"] = processed_at

            logger.info("Processed payment %s: %s -> %s", payment_id, action, new_status)
            return payment_pb2.ProcessPaymentResponse(
                payment_id=payment_id, status=new_status, processed_at=processed_at
            )

        except Exception as e:
            logger.exception("Error processing payment")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to process payment: {e}")
            return payment_pb2.ProcessPaymentResponse()

    async def HealthCheck(self, request, context):
        """Health check endpoint."""
        return payment_pb2.HealthCheckResponse(
            status="healthy",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
