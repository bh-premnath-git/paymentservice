"""Base classes and interfaces for payment processor adapters."""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict


class PaymentAdapter(ABC):
    """Abstract interface for payment processor integrations.

    Concrete implementations should translate between the service's internal
    payment model and the API of a third-party provider (e.g. Stripe).  The
    methods are intentionally minimal and return dictionaries so adapters can
    shape the response as needed.
    """

    @abstractmethod
    async def create_payment(
        self, amount: Decimal, currency: str, **kwargs: Any
    ) -> Dict[str, Any]:
        """Create a payment with the external processor."""

    @abstractmethod
    async def capture_payment(self, payment_id: str, **kwargs: Any) -> Dict[str, Any]:
        """Capture or authorise a previously created payment."""

    @abstractmethod
    async def refund_payment(self, payment_id: str, **kwargs: Any) -> Dict[str, Any]:
        """Refund a captured payment."""

    @abstractmethod
    async def cancel_payment(self, payment_id: str, **kwargs: Any) -> Dict[str, Any]:
        """Cancel a created but not yet captured payment."""

    @abstractmethod
    async def webhook_verify(
        self, payload: bytes, sig_header: str
    ) -> Dict[str, Any]:
        """Validate and parse a webhook payload from the provider."""
