import json
import os
import sys

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(ROOT_DIR)
sys.path.append(os.path.join(ROOT_DIR, "app"))

from models import Base  # noqa: E402
from payment_handler import PaymentServiceHandler  # noqa: E402
from payment.v1 import payment_pb2  # noqa: E402


@pytest.mark.asyncio
async def test_cache_uses_external_payment_id(mock_redis):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    payment_adapter = AsyncMock()
    payment_adapter.create_payment.return_value = {
        "id": "adapter-123",
        "status": "authorized",
    }

    handler = PaymentServiceHandler(sessionmaker, payment_adapter, mock_redis)

    request = payment_pb2.CreatePaymentRequest(
        amount="50.00",
        currency="USD",
        customer_id="cust-cache",
        payment_method="card",
    )
    context = MagicMock()

    response = await handler.CreatePayment(request, context)

    assert response.payment_id == "adapter-123"
    assert response.status == "authorized"

    mock_redis.setex.assert_awaited_once()
    cache_args = mock_redis.setex.await_args.args
    cache_key = handler._cache_key("adapter-123")

    assert cache_args[0] == cache_key

    cached_payload = json.loads(cache_args[2])
    assert cached_payload["payment_id"] == "adapter-123"
    assert cached_payload["status"] == "authorized"

    mock_redis.get.reset_mock()
    mock_redis.get.return_value = cache_args[2]

    payment_id = "adapter-123"
    get_response = await handler.GetPayment(
        payment_pb2.GetPaymentRequest(payment_id=payment_id), context
    )

    mock_redis.get.assert_awaited_once_with(cache_key)
    assert get_response.payment_id == "adapter-123"
    assert get_response.status == "authorized"

    await engine.dispose()
