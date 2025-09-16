import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(ROOT_DIR)
sys.path.append(os.path.join(ROOT_DIR, "app"))

from models import Base, Payment  # noqa: E402
from payment_handler import PaymentServiceHandler  # noqa: E402
from payment.v1 import payment_pb2  # noqa: E402


@pytest.mark.asyncio
async def test_process_payment_normalizes_status(mock_redis):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    payment_id = "payment_123"
    async with sessionmaker() as session:
        session.add(
            Payment(
                payment_id=payment_id,
                amount=Decimal("25.00"),
                currency="USD",
                customer_id="cust-normalize",
                payment_method="card",
                metadata_={},
                status="pending",
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    payment_adapter = AsyncMock()
    payment_adapter.capture_payment.return_value = {"status": "succeeded"}

    handler = PaymentServiceHandler(sessionmaker, payment_adapter, mock_redis)

    request = payment_pb2.ProcessPaymentRequest(payment_id=payment_id, action="capture")
    context = MagicMock()

    response = await handler.ProcessPayment(request, context)

    assert response.status == "completed"

    async with sessionmaker() as session:
        updated = await session.get(Payment, payment_id)
        assert updated.status == "completed"

    payment_adapter.capture_payment.assert_awaited_once_with(payment_id)

    mock_redis.setex.assert_awaited_once()
    cache_args = mock_redis.setex.await_args.args
    cached_payload = json.loads(cache_args[2])
    assert cached_payload["status"] == "completed"

    await engine.dispose()
