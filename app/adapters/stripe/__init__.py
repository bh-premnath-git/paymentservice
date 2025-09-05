"""Stripe payment processor adapter."""

from decimal import Decimal
from typing import Any, Dict

from ..base import PaymentAdapter


class StripeAdapter(PaymentAdapter):
    """Minimal Stripe integration placeholder.

    Real implementations should depend on the official ``stripe`` Python
    package and translate method calls to ``PaymentIntent`` API operations.
    This skeleton returns mock responses so the rest of the application can be
    developed without contacting Stripe.
    """

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def create_payment(
        self, amount: Decimal, currency: str, **kwargs: Any
    ) -> Dict[str, Any]:
        return {
            "id": "pi_mock",
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

__all__ = ["StripeAdapter"]
