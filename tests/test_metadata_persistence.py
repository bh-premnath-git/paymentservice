import os
import sys

import pytest
from unittest.mock import MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(ROOT_DIR)
sys.path.append(os.path.join(ROOT_DIR, "app"))

from models import Base, Payment
from payment_handler import PaymentServiceHandler
from payment.v1 import payment_pb2


@pytest.mark.asyncio
async def test_metadata_persistence():
    """Metadata supplied in CreatePaymentRequest should be stored in the database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    handler = PaymentServiceHandler(sessionmaker)

    metadata = {"order_id": "ABC123", "note": "test"}
    request = payment_pb2.CreatePaymentRequest(
        amount="100.00",
        currency="USD",
        customer_id="cust123",
        payment_method="card",
        metadata=metadata,
    )
    context = MagicMock()

    response = await handler.CreatePayment(request, context)

    async with sessionmaker() as session:
        payment = await session.get(Payment, response.payment_id)
        assert payment is not None
        assert payment.metadata_ == metadata

    await engine.dispose()
