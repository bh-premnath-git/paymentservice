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

