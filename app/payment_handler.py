import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import grpc
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from redis.asyncio import Redis

from payment.v1 import payment_pb2, payment_pb2_grpc
from models import Payment

logger = logging.getLogger(__name__)


class PaymentServiceHandler(payment_pb2_grpc.PaymentServiceServicer):
    """gRPC handler backed by PostgreSQL with optional Redis caching."""

    _CACHE_TTL = 300

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        redis: Optional[Redis] = None,
    ):
        self._sessionmaker = sessionmaker
        self._redis = redis
        logger.info("PaymentServiceHandler initialized")

    @staticmethod
    def _cache_key(payment_id: str) -> str:
        return f"payment:{payment_id}"

    async def CreatePayment(self, request, context):
        """Create a new payment."""
        try:
            payment_id = str(uuid.uuid4())
            created_at = datetime.now(timezone.utc)

            amount = Decimal(request.amount)

            payment = Payment(
                payment_id=payment_id,
                amount=amount,
                currency=request.currency,
                customer_id=request.customer_id,
                payment_method=request.payment_method,
                metadata_=dict(request.metadata),
                status="created",
                created_at=created_at,
            )

            async with self._sessionmaker() as session:
                session.add(payment)
                await session.commit()

            response = payment_pb2.CreatePaymentResponse(
                payment_id=payment_id,
                status="created",
                created_at=created_at.isoformat(),
            )

            if self._redis is not None:
                try:
                    await self._redis.setex(
                        self._cache_key(payment_id),
                        self._CACHE_TTL,
                        json.dumps(
                            {
                                "payment_id": payment_id,
                                "amount": str(amount),
                                "currency": request.currency,
                                "status": "created",
                                "created_at": created_at.isoformat(),
                            }
                        ),
                    )
                except Exception as exc:  # pragma: no cover - cache failure
                    logger.warning("Failed to cache payment %s: %s", payment_id, exc)

            logger.info("Created payment %s", payment_id)
            return response

        except Exception as e:
            logger.exception("Error creating payment")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to create payment: {e}")
            return payment_pb2.CreatePaymentResponse()

    async def GetPayment(self, request, context):
        """Get payment by ID."""
        try:
            payment_id = request.payment_id

            if self._redis is not None:
                try:
                    cached = await self._redis.get(self._cache_key(payment_id))
                    if cached:
                        data = json.loads(cached)
                        return payment_pb2.GetPaymentResponse(**data)
                except Exception as exc:  # pragma: no cover - cache failure
                    logger.warning("Redis lookup failed for %s: %s", payment_id, exc)

            async with self._sessionmaker() as session:
                payment = await session.get(Payment, payment_id)

            if not payment:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Payment not found: {payment_id}")
                return payment_pb2.GetPaymentResponse()

            data = {
                "payment_id": payment.payment_id,
                "amount": str(payment.amount),
                "currency": payment.currency,
                "status": payment.status,
                "created_at": payment.created_at.isoformat(),
            }

            if self._redis is not None:
                try:
                    await self._redis.setex(
                        self._cache_key(payment_id), self._CACHE_TTL, json.dumps(data)
                    )
                except Exception as exc:  # pragma: no cover - cache failure
                    logger.warning("Failed to cache payment %s: %s", payment_id, exc)

            return payment_pb2.GetPaymentResponse(**data)

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
            processed_at = datetime.now(timezone.utc)

            async with self._sessionmaker() as session:
                payment = await session.get(Payment, payment_id)
                if not payment:
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    context.set_details(f"Payment not found: {payment_id}")
                    return payment_pb2.ProcessPaymentResponse()
                payment.status = new_status
                payment.processed_at = processed_at
                await session.commit()

            response = payment_pb2.ProcessPaymentResponse(
                payment_id=payment_id,
                status=new_status,
                processed_at=processed_at.isoformat(),
            )

            if self._redis is not None:
                try:
                    await self._redis.setex(
                        self._cache_key(payment_id),
                        self._CACHE_TTL,
                        json.dumps(
                            {
                                "payment_id": payment.payment_id,
                                "amount": str(payment.amount),
                                "currency": payment.currency,
                                "status": new_status,
                                "created_at": payment.created_at.isoformat(),
                            }
                        ),
                    )
                except Exception as exc:  # pragma: no cover - cache failure
                    logger.warning(
                        "Failed to update cache for payment %s: %s", payment_id, exc
                    )

            logger.info("Processed payment %s: %s -> %s", payment_id, action, new_status)
            return response

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
