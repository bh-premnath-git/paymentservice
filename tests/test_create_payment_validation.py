import os
import sys
from unittest.mock import AsyncMock, MagicMock

import grpc
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(ROOT_DIR)
sys.path.append(os.path.join(ROOT_DIR, "app"))

from models import Base  # noqa: E402
from payment_handler import PaymentServiceHandler  # noqa: E402
from payment.v1 import payment_pb2  # noqa: E402


@pytest.mark.asyncio
async def test_create_payment_invalid_currency_sets_error():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    payment_adapter = AsyncMock()
    handler = PaymentServiceHandler(sessionmaker, payment_adapter)

    request = payment_pb2.CreatePaymentRequest(
        amount="10.00",
        currency="usd",
        customer_id="cust-invalid-currency",
        payment_method="card",
    )
    context = MagicMock()

    response = await handler.CreatePayment(request, context)

    payment_adapter.create_payment.assert_not_called()
    context.set_code.assert_called_once_with(grpc.StatusCode.INVALID_ARGUMENT)
    context.set_details.assert_called_once_with("Invalid currency code: usd")
    assert response.payment_id == ""

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_payment_invalid_amount_sets_error():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    payment_adapter = AsyncMock()
    handler = PaymentServiceHandler(sessionmaker, payment_adapter)

    request = payment_pb2.CreatePaymentRequest(
        amount="-10.00",
        currency="USD",
        customer_id="cust-invalid-amount",
        payment_method="card",
    )
    context = MagicMock()

    response = await handler.CreatePayment(request, context)

    payment_adapter.create_payment.assert_not_called()
    context.set_code.assert_called_once_with(grpc.StatusCode.INVALID_ARGUMENT)
    context.set_details.assert_called_once_with("Invalid amount: -10.00")
    assert response.payment_id == ""

    await engine.dispose()
