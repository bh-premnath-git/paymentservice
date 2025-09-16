import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

import grpc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from redis.asyncio import Redis

from payment.v1 import payment_pb2, payment_pb2_grpc
from models import Payment
from adapters.base import PaymentAdapter, validate_currency_code, validate_amount
from adapters.exceptions import PaymentError, ValidationError

logger = logging.getLogger(__name__)


class PaymentServiceHandler(payment_pb2_grpc.PaymentServiceServicer):
    """gRPC handler backed by PostgreSQL with optional Redis caching."""

    _CACHE_TTL = 300

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        payment_adapter: PaymentAdapter,
        redis: Optional[Redis] = None,
    ):
        self._sessionmaker = sessionmaker
        self._payment_adapter = payment_adapter
        self._redis = redis
        logger.info(f"PaymentServiceHandler initialized with {payment_adapter.__class__.__name__}")

    @staticmethod
    def _cache_key(payment_id: str) -> str:
        return f"payment:{payment_id}"

    async def CreatePayment(self, request, context):
        """Create a new payment using the configured payment adapter."""
        try:
            payment_id = str(uuid.uuid4())
            created_at = datetime.now(timezone.utc)
            raw_amount = request.amount

            try:
                amount = Decimal(raw_amount)
            except (InvalidOperation, TypeError) as exc:
                raise ValidationError(f"Invalid amount: {raw_amount}") from exc

            if not validate_currency_code(request.currency):
                raise ValidationError(f"Invalid currency code: {request.currency}")

            if not validate_amount(amount):
                raise ValidationError(f"Invalid amount: {raw_amount}")

            # Create payment via payment adapter (Stripe/Custom)
            try:
                adapter_result = await self._payment_adapter.create_payment(
                    amount=amount,
                    currency=request.currency,
                    customer_id=request.customer_id,
                    payment_method=request.payment_method,
                    description=f"Payment {payment_id}",
                    metadata=dict(request.metadata)
                )
                
                # Use adapter's payment ID and status
                external_payment_id = adapter_result.get("id", payment_id)
                adapter_status = adapter_result.get("status", "created")
                
                logger.info(f"Payment adapter created payment: {external_payment_id}")
                
            except PaymentError as e:
                logger.error(f"Payment adapter failed: {e}")
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details(f"Payment processing failed: {str(e)}")
                return payment_pb2.CreatePaymentResponse()
            except Exception as e:
                logger.error(f"Unexpected payment adapter error: {e}")
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"Payment system error: {str(e)}")
                return payment_pb2.CreatePaymentResponse()

            # Store payment in database with adapter results
            payment = Payment(
                payment_id=external_payment_id,  # Use adapter's ID
                amount=amount,
                currency=request.currency,
                customer_id=request.customer_id,
                payment_method=request.payment_method,
                metadata_=dict(request.metadata),
                status=adapter_status,  # Use adapter's status
                created_at=created_at,
            )

            async with self._sessionmaker() as session:
                session.add(payment)
                await session.commit()

            response = payment_pb2.CreatePaymentResponse(
                payment_id=external_payment_id,
                status=adapter_status,
                created_at=created_at.isoformat(),
            )

            if self._redis is not None:
                try:
                    await self._redis.setex(
                        self._cache_key(external_payment_id),
                        self._CACHE_TTL,
                        json.dumps(
                            {
                                "payment_id": external_payment_id,
                                "amount": str(amount),
                                "currency": request.currency,
                                "status": adapter_status,
                                "created_at": created_at.isoformat(),
                            }
                        ),
                    )
                except Exception as exc:  # pragma: no cover - cache failure
                    logger.warning(
                        "Failed to cache payment %s: %s", external_payment_id, exc
                    )

            logger.info("Created payment %s", external_payment_id)
            return response

        except ValidationError as e:
            logger.warning("Validation error creating payment: %s", e)
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return payment_pb2.CreatePaymentResponse()
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

    async def ListPayments(self, request, context):
        """List all payments."""
        try:
            async with self._sessionmaker() as session:
                result = await session.execute(select(Payment))
                payments = result.scalars().all()

            payment_list = [
                payment_pb2.GetPaymentResponse(
                    payment_id=p.payment_id,
                    amount=str(p.amount),
                    currency=p.currency,
                    status=p.status,
                    created_at=p.created_at.isoformat(),
                )
                for p in payments
            ]
            return payment_pb2.ListPaymentsResponse(payments=payment_list)
        except Exception as e:
            logger.exception("Error listing payments")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to list payments: {e}")
            return payment_pb2.ListPaymentsResponse()

    async def ProcessPayment(self, request, context):
        """Process payment action using payment adapter."""
        try:
            payment_id = request.payment_id
            action = request.action
            processed_at = datetime.now(timezone.utc)

            # Get payment from database first
            async with self._sessionmaker() as session:
                payment = await session.get(Payment, payment_id)
                if not payment:
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    context.set_details(f"Payment not found: {payment_id}")
                    return payment_pb2.ProcessPaymentResponse()

            # Process action via payment adapter
            try:
                if action == "capture":
                    adapter_result = await self._payment_adapter.capture_payment(payment_id)
                elif action == "refund":
                    adapter_result = await self._payment_adapter.refund_payment(payment_id)
                elif action == "cancel":
                    adapter_result = await self._payment_adapter.cancel_payment(payment_id)
                else:
                    context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                    context.set_details(f"Unknown action: {action}")
                    return payment_pb2.ProcessPaymentResponse()

                new_status = adapter_result.get("status", action + "d")
                logger.info(f"Payment {payment_id} {action} via adapter: {new_status}")

            except PaymentError as e:
                logger.error(f"Payment adapter {action} failed: {e}")
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details(f"Payment {action} failed: {str(e)}")
                return payment_pb2.ProcessPaymentResponse()
            except Exception as e:
                logger.error(f"Unexpected payment adapter error during {action}: {e}")
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"Payment system error: {str(e)}")
                return payment_pb2.ProcessPaymentResponse()

            # Update database with adapter results
            async with self._sessionmaker() as session:
                payment = await session.get(Payment, payment_id)
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
