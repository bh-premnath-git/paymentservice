import os
import sys

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(ROOT_DIR)

from sandbox.requestor_mock.main import (
    PaymentGRPCClient,
    PaymentRequest,
    PaymentInput,
    create_payment_rest,
    Mutation,
    grpc_client,
)


@pytest.mark.asyncio
async def test_grpc_client_forwards_metadata():
    client = PaymentGRPCClient()
    stub = SimpleNamespace()
    stub.CreatePayment = AsyncMock(return_value=SimpleNamespace(payment_id="1", status="created", created_at="now"))
    client.stub = stub

    payload = PaymentRequest(amount="10.00", customer_id="cust", payment_method="card", metadata={"foo": "bar"})

    await client.create_payment(payload)

    sent_request = stub.CreatePayment.call_args[0][0]
    assert dict(sent_request.metadata) == {"foo": "bar"}


@pytest.mark.asyncio
async def test_rest_endpoint_propagates_metadata(monkeypatch):
    metadata = {"order": "123"}
    mock_create = AsyncMock(return_value={})
    monkeypatch.setattr(grpc_client, "create_payment", mock_create)

    request = PaymentRequest(amount="5.00", customer_id="cust", payment_method="card", metadata=metadata)
    await create_payment_rest(request)

    sent_request = mock_create.call_args[0][0]
    assert sent_request.metadata == metadata


@pytest.mark.asyncio
async def test_graphql_endpoint_propagates_metadata(monkeypatch):
    metadata = {"note": "test"}
    mock_create = AsyncMock(return_value={"payment_id": "1", "status": "created", "created_at": "now"})
    mock_get = AsyncMock(return_value={
        "payment_id": "1",
        "amount": "5.00",
        "currency": "USD",
        "status": "created",
        "created_at": "now",
    })
    monkeypatch.setattr(grpc_client, "create_payment", mock_create)
    monkeypatch.setattr(grpc_client, "get_payment", mock_get)

    payload = PaymentInput(amount="5.00", customer_id="cust", metadata=metadata)
    mutation = Mutation()
    await mutation.create_payment(payload)

    sent_request = mock_create.call_args[0][0]
    assert sent_request.metadata == metadata
