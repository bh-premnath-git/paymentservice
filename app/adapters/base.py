"""Base classes and exceptions for payment processing."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from decimal import Decimal

from .exceptions import (
    PaymentError,
    ValidationError,
    InsufficientFundsError,
    PaymentNotFoundError,
    PaymentProcessingError,
    RefundError,
    WebhookError,
    RateLimitError,
    AuthenticationError,
)


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
            
        Raises:
            ValidationError: If input parameters are invalid
            InsufficientFundsError: If payment fails due to insufficient funds
            PaymentProcessingError: If payment processing fails
            AuthenticationError: If authentication with payment processor fails
            RateLimitError: If API rate limits are exceeded
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
            
        Raises:
            PaymentNotFoundError: If payment ID is not found
            PaymentProcessingError: If capture fails
            ValidationError: If payment cannot be captured (wrong status)
            AuthenticationError: If authentication with payment processor fails
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
            
        Raises:
            PaymentNotFoundError: If payment ID is not found
            RefundError: If refund processing fails
            ValidationError: If refund parameters are invalid
            AuthenticationError: If authentication with payment processor fails
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
            
        Raises:
            PaymentNotFoundError: If payment ID is not found
            PaymentProcessingError: If cancellation fails
            ValidationError: If payment cannot be cancelled (wrong status)
            AuthenticationError: If authentication with payment processor fails
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
            WebhookError: If verification fails or payload is invalid
            ValidationError: If signature or payload format is invalid
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
            
        Raises:
            PaymentNotFoundError: If payment ID is not found
            PaymentProcessingError: If status retrieval fails
            AuthenticationError: If authentication with payment processor fails
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
            
        Raises:
            ValidationError: If filter parameters are invalid
            PaymentProcessingError: If listing fails
            AuthenticationError: If authentication with payment processor fails
            RateLimitError: If API rate limits are exceeded
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
            Dictionary containing rate information:
            {
                'rate': Decimal,
                'from_currency': str,
                'to_currency': str,
                'timestamp': datetime,
                'expires_at': Optional[datetime]
            }
            
        Raises:
            ValidationError: If currency codes are invalid
            PaymentProcessingError: If rate retrieval fails
            RateLimitError: If API rate limits are exceeded
        """
        pass
    
    @abstractmethod
    async def convert_amount(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str
    ) -> Dict[str, Any]:
        """Convert amount between currencies.
        
        Args:
            amount: Amount to convert
            from_currency: Source currency code
            to_currency: Target currency code
            
        Returns:
            Dictionary containing conversion details:
            {
                'original_amount': Decimal,
                'converted_amount': Decimal,
                'rate': Decimal,
                'from_currency': str,
                'to_currency': str,
                'timestamp': datetime
            }
            
        Raises:
            ValidationError: If currency codes or amount are invalid
            PaymentProcessingError: If conversion fails
        """
        pass


# ==================== Utility Functions ====================

def validate_currency_code(currency: str) -> bool:
    """Validate ISO 4217 currency code format.
    
    Args:
        currency: Currency code to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(currency, str):
        return False
    return len(currency) == 3 and currency.isalpha() and currency.isupper()


def validate_amount(amount: Decimal) -> bool:
    """Validate payment amount.
    
    Args:
        amount: Amount to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(amount, Decimal):
        return False
    return amount > 0 and amount.is_finite()


def normalize_payment_status(status: str) -> str:
    """Normalize payment status across different processors.
    
    Args:
        status: Raw status from payment processor
        
    Returns:
        Normalized status string
    """
    status_mapping = {
        # Common statuses
        'pending': 'pending',
        'processing': 'processing', 
        'succeeded': 'completed',
        'completed': 'completed',
        'failed': 'failed',
        'canceled': 'cancelled',
        'cancelled': 'cancelled',
        'refunded': 'refunded',
        'partially_refunded': 'partially_refunded',
        
        # Stripe specific
        'requires_payment_method': 'pending',
        'requires_confirmation': 'pending',
        'requires_action': 'pending',
        'requires_capture': 'authorized',
        'payment_failed': 'failed',
    }
    
    return status_mapping.get(status.lower(), status.lower())