"""Base classes and exceptions for payment processing."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from decimal import Decimal


# ==================== Exceptions ====================

class PaymentError(Exception):
    """Base exception for payment-related errors."""
    pass


class ValidationError(PaymentError):
    """Raised when input validation fails."""
    pass


class InsufficientFundsError(PaymentError):
    """Raised when payment fails due to insufficient funds."""
    pass


class PaymentNotFoundError(PaymentError):
    """Raised when a payment cannot be found."""
    pass


class PaymentProcessingError(PaymentError):
    """Raised when payment processing fails."""
    pass


class RefundError(PaymentError):
    """Raised when refund processing fails."""
    pass


class WebhookError(PaymentError):
    """Raised when webhook processing fails."""
    pass


class RateLimitError(PaymentError):
    """Raised when API rate limits are exceeded."""
    pass


class AuthenticationError(PaymentError):
    """Raised when authentication fails."""
    pass


# ==================== Base Adapter ====================

class PaymentAdapter(ABC):
    """Abstract base class for payment processor adapters."""
    
    @abstractmethod
    async def create_payment(
        self, 
        amount: Decimal, 
        currency: str, 
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Create a new payment transaction.
        
        Args:
            amount: Payment amount in smallest currency unit
            currency: Three-letter ISO currency code
            **kwargs: Additional processor-specific parameters
            
        Returns:
            Payment details including ID and status
        """
        pass
    
    @abstractmethod
    async def capture_payment(
        self, 
        payment_id: str, 
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Capture a previously authorized payment.
        
        Args:
            payment_id: Unique payment identifier
            **kwargs: Additional processor-specific parameters
            
        Returns:
            Updated payment details
        """
        pass
    
    @abstractmethod
    async def refund_payment(
        self, 
        payment_id: str, 
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Refund a payment (full or partial).
        
        Args:
            payment_id: Unique payment identifier
            **kwargs: Additional parameters (e.g., amount for partial refund)
            
        Returns:
            Refund details
        """
        pass
    
    @abstractmethod
    async def cancel_payment(
        self, 
        payment_id: str, 
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Cancel a pending payment.
        
        Args:
            payment_id: Unique payment identifier
            **kwargs: Additional processor-specific parameters
            
        Returns:
            Updated payment details
        """
        pass
    
    @abstractmethod
    async def webhook_verify(
        self, 
        payload: bytes, 
        sig_header: str
    ) -> Dict[str, Any]:
        """Verify and parse webhook payload.
        
        Args:
            payload: Raw webhook payload
            sig_header: Signature header for verification
            
        Returns:
            Parsed and verified webhook data
            
        Raises:
            WebhookError: If verification fails
        """
        pass
    
    async def get_payment_status(
        self, 
        payment_id: str
    ) -> Dict[str, Any]:
        """Get current payment status.
        
        Args:
            payment_id: Unique payment identifier
            
        Returns:
            Payment status and details
        """
        raise NotImplementedError("Payment status check not implemented")
    
    async def list_payments(
        self, 
        limit: int = 10,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """List recent payments.
        
        Args:
            limit: Maximum number of payments to return
            **kwargs: Additional filter parameters
            
        Returns:
            List of payment records
        """
        raise NotImplementedError("Payment listing not implemented")


# ==================== Custom FX Service Interface ====================

class FXRateService(ABC):
    """Abstract base class for custom FX rate providers."""
    
    @abstractmethod
    async def get_rate(
        self,
        from_currency: str,
        to_currency: str,
        amount: Optional[Decimal] = None
    ) -> Dict[str, Any]:
        """Get exchange rate between currencies.
        
        Args:
            from_currency: Source currency code
            to_currency: Target currency code
            amount: Optional amount for tiered rates
            
        Returns:
            Exchange rate details including rate and fees
        """
        pass
    
    @abstractmethod
    async def convert_amount(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        include_fees: bool = True
    ) -> Dict[str, Any]:
        """Convert amount between currencies.
        
        Args:
            amount: Amount to convert
            from_currency: Source currency code
            to_currency: Target currency code
            include_fees: Whether to include conversion fees
            
        Returns:
            Converted amount and rate details
        """
        pass
    
    @abstractmethod
    async def lock_rate(
        self,
        from_currency: str,
        to_currency: str,
        duration_minutes: int = 60
    ) -> Dict[str, Any]:
        """Lock an exchange rate for a specified duration.
        
        Args:
            from_currency: Source currency code
            to_currency: Target currency code
            duration_minutes: Lock duration in minutes
            
        Returns:
            Rate lock details including ID and expiration
        """
        pass