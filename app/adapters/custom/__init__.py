"""Example custom payment processor adapter."""

import json
from json import JSONDecodeError
from decimal import Decimal
from typing import Any, Dict

from ..base import PaymentAdapter
from ..exceptions import WebhookError


class CustomAdapter(PaymentAdapter):
    """Simple in-house payment processor implementation.

    This adapter is entirely self-contained and can be adjusted to match any
    bespoke gateway.  It mirrors the ``PaymentAdapter`` interface and returns
    predictable mock responses suitable for testing and local development.
    """

    def __init__(self, expected_signature: str = "test_signature") -> None:
        """Create a CustomAdapter.

        Args:
            expected_signature: Signature header value considered valid.  This
                keeps webhook verification deterministic for tests while still
                exercising signature handling logic.
        """
        super().__init__()
        self.expected_signature = expected_signature

    async def create_payment(
        self, amount: Decimal, currency: str, **kwargs: Any
    ) -> Dict[str, Any]:
        return {
            "id": "custom_mock",
            "amount": str(amount),
            "currency": currency,
            "status": "created",
        }

    async def capture_payment(self, payment_id: str, **kwargs: Any) -> Dict[str, Any]:
        return {"id": payment_id, "status": "captured"}

    async def refund_payment(self, payment_id: str, **kwargs: Any) -> Dict[str, Any]:
        return {"id": payment_id, "status": "refunded"}

    async def cancel_payment(self, payment_id: str, **kwargs: Any) -> Dict[str, Any]:
        return {"id": payment_id, "status": "cancelled"}

    async def webhook_verify(
        self, payload: bytes, sig_header: str
    ) -> Dict[str, Any]:
        if not sig_header:
            raise WebhookError("Missing webhook signature header")

        if sig_header != self.expected_signature:
            raise WebhookError("Invalid webhook signature")

        try:
            decoded_payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WebhookError("Invalid webhook payload encoding") from exc

        try:
            data = json.loads(decoded_payload)
        except JSONDecodeError as exc:
            raise WebhookError("Invalid webhook payload") from exc

        return {"type": data.get("type", "unknown"), "data": data.get("data", {})}


__all__ = ["CustomAdapter"]
