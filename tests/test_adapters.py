"""
Test all payment adapters functionality.
"""

import os
import sys
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(ROOT_DIR)
sys.path.append(os.path.join(ROOT_DIR, "app"))

from adapters.base import PaymentAdapter, validate_currency_code, validate_amount, normalize_payment_status
from adapters.custom import CustomAdapter
from adapters.exceptions import (
    PaymentError,
    ValidationError,
    InsufficientFundsError,
    PaymentNotFoundError,
    PaymentProcessingError,
    RefundError,
    WebhookError,
    RateLimitError,
    AuthenticationError
)


class TestPaymentAdapterBase:
    """Test the base PaymentAdapter functionality."""
    
    def test_validate_currency_code(self):
        """Test currency code validation."""
        assert validate_currency_code("USD") is True
        assert validate_currency_code("EUR") is True
        assert validate_currency_code("GBP") is True
        
        assert validate_currency_code("usd") is False  # lowercase
        assert validate_currency_code("US") is False   # too short
        assert validate_currency_code("USDD") is False # too long
        assert validate_currency_code(123) is False    # not string
        assert validate_currency_code("") is False     # empty

    def test_validate_amount(self):
        """Test amount validation."""
        assert validate_amount(Decimal("10.00")) is True
        assert validate_amount(Decimal("0.01")) is True
        assert validate_amount(Decimal("1000000.99")) is True
        
        assert validate_amount(Decimal("0")) is False     # zero
        assert validate_amount(Decimal("-10.00")) is False # negative
        assert validate_amount("10.00") is False          # not Decimal
        assert validate_amount(10.00) is False            # float

    def test_normalize_payment_status(self):
        """Test payment status normalization."""
        # Standard statuses
        assert normalize_payment_status("pending") == "pending"
        assert normalize_payment_status("succeeded") == "completed"
        assert normalize_payment_status("failed") == "failed"
        assert normalize_payment_status("canceled") == "cancelled"
        
        # Stripe specific
        assert normalize_payment_status("requires_payment_method") == "pending"
        assert normalize_payment_status("requires_capture") == "authorized"
        assert normalize_payment_status("payment_failed") == "failed"
        
        # Case insensitive
        assert normalize_payment_status("SUCCEEDED") == "completed"
        assert normalize_payment_status("Failed") == "failed"
        
        # Unknown status
        assert normalize_payment_status("unknown_status") == "unknown_status"


class TestCustomAdapter:
    """Test CustomAdapter implementation."""
    
    @pytest.fixture
    def adapter(self):
        """Create CustomAdapter instance."""
        return CustomAdapter()

    @pytest.mark.asyncio
    async def test_create_payment(self, adapter):
        """Test payment creation."""
        result = await adapter.create_payment(
            amount=Decimal('25.50'),
            currency='EUR',
            description='Test payment'
        )
        
        assert result['id'] == 'custom_mock'
        assert result['amount'] == '25.50'
        assert result['currency'] == 'EUR'
        assert result['status'] == 'created'

    @pytest.mark.asyncio
    async def test_capture_payment(self, adapter):
        """Test payment capture."""
        result = await adapter.capture_payment('test_payment_123')
        
        assert result['id'] == 'test_payment_123'
        assert result['status'] == 'captured'

    @pytest.mark.asyncio
    async def test_refund_payment(self, adapter):
        """Test payment refund."""
        result = await adapter.refund_payment(
            'test_payment_123',
            amount=Decimal('10.00')
        )
        
        assert result['id'] == 'test_payment_123'
        assert result['status'] == 'refunded'

    @pytest.mark.asyncio
    async def test_cancel_payment(self, adapter):
        """Test payment cancellation."""
        result = await adapter.cancel_payment('test_payment_123')
        
        assert result['id'] == 'test_payment_123'
        assert result['status'] == 'cancelled'

    @pytest.mark.asyncio
    async def test_webhook_verify(self, adapter):
        """Test webhook verification."""
        payload = b'{"type": "payment.completed", "data": {"id": "pay_123", "amount": 1000}}'
        sig_header = 'test_signature'
        
        result = await adapter.webhook_verify(payload, sig_header)
        
        assert result['type'] == 'payment.completed'
        assert result['data']['id'] == 'pay_123'
        assert result['data']['amount'] == 1000

    @pytest.mark.asyncio
    async def test_webhook_verify_invalid_json(self, adapter):
        """Test webhook verification with invalid JSON."""
        payload = b'invalid json'
        sig_header = 'test_signature'
        
        with pytest.raises(Exception):  # Should raise JSON decode error
            await adapter.webhook_verify(payload, sig_header)

    @pytest.mark.asyncio
    async def test_get_payment_status_not_implemented(self, adapter):
        """Test that get_payment_status raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await adapter.get_payment_status('test_payment_123')

    @pytest.mark.asyncio
    async def test_list_payments_not_implemented(self, adapter):
        """Test that list_payments raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await adapter.list_payments()


class TestAdapterExceptions:
    """Test payment adapter exceptions."""
    
    def test_payment_error_hierarchy(self):
        """Test that all payment exceptions inherit from PaymentError."""
        exceptions = [
            ValidationError,
            InsufficientFundsError,
            PaymentNotFoundError,
            PaymentProcessingError,
            RefundError,
            WebhookError,
            RateLimitError,
            AuthenticationError
        ]
        
        for exc_class in exceptions:
            assert issubclass(exc_class, PaymentError)
            
            # Test instantiation
            exc_instance = exc_class("Test error message")
            assert isinstance(exc_instance, PaymentError)
            assert str(exc_instance) == "Test error message"

    def test_exception_inheritance_chain(self):
        """Test specific exception inheritance."""
        # All should inherit from Exception via PaymentError
        assert issubclass(PaymentError, Exception)
        assert issubclass(ValidationError, Exception)
        assert issubclass(InsufficientFundsError, Exception)


@pytest.mark.skipif(
    not os.getenv('STRIPE_SECRET_KEY'),
    reason="Stripe credentials not available"
)
class TestStripeAdapterIntegration:
    """Integration tests for Stripe adapter (requires credentials)."""
    
    @pytest.fixture
    def stripe_adapter(self):
        """Create StripeAdapter with test credentials."""
        from adapters.stripe import StripeAdapter
        
        return StripeAdapter(
            api_key=os.getenv('STRIPE_SECRET_KEY'),
            webhook_secret=os.getenv('STRIPE_WEBHOOK_SECRET'),
            enable_test_mode=True
        )

    def test_stripe_adapter_initialization(self, stripe_adapter):
        """Test Stripe adapter initializes correctly."""
        assert stripe_adapter is not None
        assert stripe_adapter.test_mode is True

    @pytest.mark.asyncio
    async def test_stripe_webhook_verification_with_mock(self, stripe_adapter):
        """Test webhook verification with mocked Stripe call."""
        mock_event = {
            'id': 'evt_test123',
            'type': 'payment_intent.succeeded',
            'created': 1234567890,
            'livemode': False,
            'data': {
                'object': {
                    'id': 'pi_test123',
                    'object': 'payment_intent',
                    'amount': 1000,
                    'currency': 'usd',
                    'status': 'succeeded',
                    'created': 1234567890,
                    'livemode': False
                }
            }
        }
        
        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = mock_event
            
            result = await stripe_adapter.webhook_verify(
                payload=b'{"test": "webhook"}',
                sig_header='test_signature'
            )
            
            assert result['id'] == 'evt_test123'
            assert result['type'] == 'payment_intent.succeeded'
            assert result['data']['id'] == 'pi_test123'
            assert result['data']['amount'] == 1000


class TestAdapterFactory:
    """Test adapter selection and factory patterns."""
    
    def test_provider_selection_logic(self):
        """Test the provider selection logic from main.py."""
        # Test with environment variables set
        with patch.dict(os.environ, {
            'STRIPE_SECRET_KEY': 'sk_test_123',
            'STRIPE_WEBHOOK_SECRET': 'whsec_123'
        }):
            from main import get_provider
            get_provider.cache_clear()  # Clear LRU cache
            
            provider = get_provider()
            # Should be StripeAdapter when keys are available
            assert provider.__class__.__name__ == 'StripeAdapter'
        
        # Test without environment variables
        with patch.dict(os.environ, {}, clear=True):
            from main import get_provider
            get_provider.cache_clear()  # Clear LRU cache
            
            provider = get_provider()
            # Should be CustomAdapter when no keys
            assert isinstance(provider, CustomAdapter)

    def test_multiple_adapter_support(self):
        """Test that architecture supports multiple payment providers."""
        adapters = [CustomAdapter]
        
        # Try to import StripeAdapter
        try:
            from adapters.stripe import StripeAdapter
            adapters.append(StripeAdapter)
        except ImportError:
            pass  # Stripe not available
        
        # All adapters should inherit from PaymentAdapter
        for adapter_class in adapters:
            assert issubclass(adapter_class, PaymentAdapter)
            
            # All should implement required methods
            required_methods = [
                'create_payment',
                'capture_payment',
                'refund_payment',
                'cancel_payment',
                'webhook_verify'
            ]
            
            for method in required_methods:
                assert hasattr(adapter_class, method)
                assert callable(getattr(adapter_class, method))