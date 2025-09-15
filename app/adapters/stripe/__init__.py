"""Stripe payment processor adapter."""

from decimal import Decimal
from typing import Any, Dict

import stripe
from ..base import PaymentAdapter


class StripeAdapter(PaymentAdapter):
    """Minimal Stripe integration placeholder.

    Real implementations should depend on the official ``stripe`` Python
    package and translate method calls to ``PaymentIntent`` API operations.
    This skeleton returns mock responses so the rest of the application can be
    developed without contacting Stripe.
    """

    def __init__(self, api_key: str, webhook_secret: str) -> None:
        stripe.api_key = api_key
        self.webhook_secret = webhook_secret

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

    async def webhook_verify(
        self, payload: bytes, sig_header: str
    ) -> Dict[str, Any]:
        event = stripe.Webhook.construct_event(
            payload, sig_header, self.webhook_secret
        )
        return {"type": event["type"], "data": event["data"]["object"]}

__all__ = ["StripeAdapter"]
