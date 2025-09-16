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
async def test_list_payments_returns_all():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    payment_adapter = AsyncMock()
    payment_adapter.create_payment.return_value = {"status": "created"}
    handler = PaymentServiceHandler(sessionmaker, payment_adapter)

    ctx = MagicMock()
    req = payment_pb2.CreatePaymentRequest(
        amount="10.00",
        currency="USD",
        customer_id="cust1",
        payment_method="card",
    )
    resp1 = await handler.CreatePayment(req, ctx)
    resp2 = await handler.CreatePayment(req, ctx)

    list_resp = await handler.ListPayments(payment_pb2.ListPaymentsRequest(), ctx)

    ids = {p.payment_id for p in list_resp.payments}
    assert {resp1.payment_id, resp2.payment_id} <= ids

    await engine.dispose()
