"""Example custom payment processor adapter."""

from decimal import Decimal
from typing import Any, Dict
import json

from ..base import PaymentAdapter


class CustomAdapter(PaymentAdapter):
    """Simple in-house payment processor implementation.

    This adapter is entirely self-contained and can be adjusted to match any
    bespoke gateway.  It mirrors the ``PaymentAdapter`` interface and returns
    predictable mock responses suitable for testing and local development.
    """

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
        data = json.loads(payload.decode())
        return {"type": data.get("type", "unknown"), "data": data.get("data", {})}

__all__ = ["CustomAdapter"]
