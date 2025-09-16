"""
Contract tests to verify all payment adapters implement the PaymentAdapter interface correctly.
These tests ensure any new payment provider adapter follows the established contract.
"""

import os
import sys
import pytest
import inspect
from decimal import Decimal
from typing import Dict, Any
from unittest.mock import AsyncMock, patch

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(ROOT_DIR)
sys.path.append(os.path.join(ROOT_DIR, "app"))

from adapters.base import PaymentAdapter
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


def get_all_adapter_classes():
    """Get all available adapter classes for testing."""
    adapters = [CustomAdapter]
    
    # Try to import additional adapters
    try:
        from adapters.stripe import StripeAdapter
        adapters.append(StripeAdapter)
    except ImportError:
        pass
    
    return adapters


class TestPaymentAdapterContract:
    """Test that all adapters conform to the PaymentAdapter contract."""
    
    @pytest.mark.parametrize("adapter_class", get_all_adapter_classes())
    def test_adapter_inherits_from_base(self, adapter_class):
        """Verify adapter inherits from PaymentAdapter."""
        assert issubclass(adapter_class, PaymentAdapter)
    
    @pytest.mark.parametrize("adapter_class", get_all_adapter_classes())
    def test_adapter_implements_required_methods(self, adapter_class):
        """Verify adapter implements all required abstract methods."""
        required_methods = {
            'create_payment': True,
            'capture_payment': True, 
            'refund_payment': True,
            'cancel_payment': True,
            'webhook_verify': True,
        }
        
        for method_name, is_required in required_methods.items():
            assert hasattr(adapter_class, method_name), f"{adapter_class.__name__} missing {method_name}"
            method = getattr(adapter_class, method_name)
            assert callable(method), f"{adapter_class.__name__}.{method_name} is not callable"
            
            if is_required:
                # Check that method is not the abstract base implementation
                base_method = getattr(PaymentAdapter, method_name, None)
                if base_method:
                    assert method != base_method, f"{adapter_class.__name__}.{method_name} not implemented"
    
    @pytest.mark.parametrize("adapter_class", get_all_adapter_classes())
    def test_adapter_method_signatures(self, adapter_class):
        """Verify adapter methods have correct signatures."""
        # Check create_payment signature
        create_payment = getattr(adapter_class, 'create_payment')
        sig = inspect.signature(create_payment)
        
        # Should have at least amount, currency parameters
        param_names = list(sig.parameters.keys())
        assert 'self' in param_names
        assert 'amount' in param_names
        assert 'currency' in param_names
        assert 'kwargs' in param_names or any('**' in str(p) for p in sig.parameters.values())
        
        # Check webhook_verify signature
        webhook_verify = getattr(adapter_class, 'webhook_verify')
        sig = inspect.signature(webhook_verify)
        param_names = list(sig.parameters.keys())
        assert 'self' in param_names
        assert 'payload' in param_names
        assert 'sig_header' in param_names


class TestAdapterContractCompliance:
    """Test adapter contract compliance with actual method calls."""
    
    @pytest.fixture(params=get_all_adapter_classes())
    def adapter_instance(self, request):
        """Create adapter instances for testing."""
        adapter_class = request.param
        
        if adapter_class.__name__ == 'StripeAdapter':
            # Mock Stripe adapter initialization
            with patch('stripe.api_key'):
                return adapter_class(
                    api_key='sk_test_fake',
                    webhook_secret='whsec_fake',
                    enable_test_mode=True
                )
        else:
            return adapter_class()
    
    @pytest.mark.asyncio
    async def test_create_payment_contract(self, adapter_instance):
        """Test create_payment follows contract."""
        # Mock external API calls for Stripe
        if adapter_instance.__class__.__name__ == 'StripeAdapter':
            mock_payment_intent = AsyncMock()
            mock_payment_intent.id = 'pi_test123'
            mock_payment_intent.client_secret = 'pi_test123_secret'
            mock_payment_intent.amount = 1000
            mock_payment_intent.currency = 'usd'
            mock_payment_intent.status = 'requires_payment_method'
            mock_payment_intent.created = 1234567890
            mock_payment_intent.metadata = {}
            
            with patch('stripe.PaymentIntent.create', return_value=mock_payment_intent):
                result = await adapter_instance.create_payment(
                    amount=Decimal('10.00'),
                    currency='USD',
                    customer_id='cust_test123'
                )
        else:
            result = await adapter_instance.create_payment(
                amount=Decimal('10.00'),
                currency='USD'
            )
        
        # Verify return type and required fields
        assert isinstance(result, dict)
        assert 'id' in result
        assert 'status' in result
        assert isinstance(result['id'], str)
        assert isinstance(result['status'], str)
    
    @pytest.mark.asyncio
    async def test_capture_payment_contract(self, adapter_instance):
        """Test capture_payment follows contract."""
        if adapter_instance.__class__.__name__ == 'StripeAdapter':
            mock_payment_intent = AsyncMock()
            mock_payment_intent.id = 'pi_test123'
            mock_payment_intent.status = 'succeeded'
            mock_payment_intent.amount = 1000
            mock_payment_intent.currency = 'usd'
            mock_payment_intent.created = 1234567890
            mock_payment_intent.metadata = {}
            
            with patch('stripe.PaymentIntent.capture', return_value=mock_payment_intent):
                result = await adapter_instance.capture_payment('pi_test123')
        else:
            result = await adapter_instance.capture_payment('test_payment_id')
        
        # Verify return type and required fields
        assert isinstance(result, dict)
        assert 'id' in result
        assert 'status' in result
    
    @pytest.mark.asyncio
    async def test_webhook_verify_contract(self, adapter_instance):
        """Test webhook_verify follows contract."""
        payload = b'{"type": "payment.succeeded", "data": {"id": "test_123"}}'
        sig_header = 'test_signature'
        
        if adapter_instance.__class__.__name__ == 'StripeAdapter':
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
            
            with patch('stripe.Webhook.construct_event', return_value=mock_event):
                result = await adapter_instance.webhook_verify(payload, sig_header)
        else:
            result = await adapter_instance.webhook_verify(payload, sig_header)
        
        # Verify return type and required fields
        assert isinstance(result, dict)
        assert 'type' in result
        assert 'data' in result


class TestAdapterErrorHandling:
    """Test that adapters handle errors consistently."""
    
    @pytest.fixture
    def custom_adapter(self):
        """Create CustomAdapter for error testing."""
        return CustomAdapter()
    
    @pytest.mark.asyncio
    async def test_webhook_verify_invalid_json(self, custom_adapter):
        """Test webhook verification with invalid JSON raises appropriate error."""
        invalid_payload = b'invalid json data'
        sig_header = 'test_signature'
        
        with pytest.raises(Exception):  # Should raise some form of error
            await custom_adapter.webhook_verify(invalid_payload, sig_header)
    
    def test_exception_hierarchy_completeness(self):
        """Test that all payment exceptions are properly defined."""
        expected_exceptions = [
            'PaymentError',
            'ValidationError', 
            'InsufficientFundsError',
            'PaymentNotFoundError',
            'PaymentProcessingError',
            'RefundError',
            'WebhookError',
            'RateLimitError',
            'AuthenticationError'
        ]
        
        from adapters import exceptions
        
        for exc_name in expected_exceptions:
            assert hasattr(exceptions, exc_name), f"Missing exception: {exc_name}"
            exc_class = getattr(exceptions, exc_name)
            assert issubclass(exc_class, Exception)
            
            if exc_name != 'PaymentError':
                assert issubclass(exc_class, PaymentError)


class TestAdapterUtilities:
    """Test adapter utility functions."""
    
    def test_currency_validation(self):
        """Test currency code validation utility."""
        from adapters.base import validate_currency_code
        
        # Valid currencies
        assert validate_currency_code("USD") is True
        assert validate_currency_code("EUR") is True
        assert validate_currency_code("GBP") is True
        assert validate_currency_code("JPY") is True
        
        # Invalid currencies
        assert validate_currency_code("usd") is False    # lowercase
        assert validate_currency_code("US") is False     # too short
        assert validate_currency_code("USDD") is False   # too long
        assert validate_currency_code("123") is False    # numeric
        assert validate_currency_code("") is False       # empty
        assert validate_currency_code(None) is False     # None
    
    def test_amount_validation(self):
        """Test amount validation utility."""
        from adapters.base import validate_amount
        
        # Valid amounts
        assert validate_amount(Decimal("0.01")) is True
        assert validate_amount(Decimal("10.00")) is True
        assert validate_amount(Decimal("1000000.99")) is True
        
        # Invalid amounts
        assert validate_amount(Decimal("0")) is False      # zero
        assert validate_amount(Decimal("-1.00")) is False  # negative
        assert validate_amount(10.0) is False              # float
        assert validate_amount("10.00") is False           # string
        assert validate_amount(None) is False              # None
    
    def test_status_normalization(self):
        """Test payment status normalization utility."""
        from adapters.base import normalize_payment_status
        
        # Standard normalizations
        assert normalize_payment_status("pending") == "pending"
        assert normalize_payment_status("succeeded") == "completed"
        assert normalize_payment_status("completed") == "completed"
        assert normalize_payment_status("failed") == "failed"
        assert normalize_payment_status("canceled") == "cancelled"
        assert normalize_payment_status("cancelled") == "cancelled"
        
        # Provider-specific normalizations
        assert normalize_payment_status("requires_payment_method") == "pending"
        assert normalize_payment_status("requires_capture") == "authorized"
        assert normalize_payment_status("payment_failed") == "failed"
        
        # Case insensitive
        assert normalize_payment_status("SUCCEEDED") == "completed"
        assert normalize_payment_status("Failed") == "failed"
        
        # Unknown status passthrough
        assert normalize_payment_status("unknown_status") == "unknown_status"


class TestAdapterScalability:
    """Test that the adapter pattern scales for multiple providers."""
    
    def test_adapter_registration_pattern(self):
        """Test that new adapters can be easily registered."""
        # Simulate adding a new adapter
        class MockPayPalAdapter(PaymentAdapter):
            async def create_payment(self, amount, currency, **kwargs):
                return {"id": "paypal_123", "status": "created"}
            
            async def capture_payment(self, payment_id, **kwargs):
                return {"id": payment_id, "status": "captured"}
            
            async def refund_payment(self, payment_id, **kwargs):
                return {"id": payment_id, "status": "refunded"}
            
            async def cancel_payment(self, payment_id, **kwargs):
                return {"id": payment_id, "status": "cancelled"}
            
            async def webhook_verify(self, payload, sig_header):
                return {"type": "payment.completed", "data": {}}
        
        # Verify it follows the contract
        assert issubclass(MockPayPalAdapter, PaymentAdapter)
        
        # Test instantiation and basic method calls
        adapter = MockPayPalAdapter()
        assert adapter is not None
    
    def test_provider_factory_extensibility(self):
        """Test that provider factory can be extended."""
        # Test current provider selection logic
        from main import get_provider
        
        # Should return some adapter
        provider = get_provider()
        assert isinstance(provider, PaymentAdapter)
        
        # Verify it's either Stripe or Custom
        adapter_name = provider.__class__.__name__
        assert adapter_name in ['StripeAdapter', 'CustomAdapter']
    
    @pytest.mark.asyncio
    async def test_adapter_interface_consistency(self):
        """Test that all adapters return consistent response formats."""
        adapters = [CustomAdapter()]
        
        # Try to add Stripe adapter if available
        try:
            from adapters.stripe import StripeAdapter
            with patch('stripe.api_key'):
                stripe_adapter = StripeAdapter(
                    api_key='sk_test_fake',
                    webhook_secret='whsec_fake'
                )
                adapters.append(stripe_adapter)
        except ImportError:
            pass
        
        # Test that all adapters return similar structures
        for adapter in adapters:
            if adapter.__class__.__name__ == 'StripeAdapter':
                # Mock Stripe API for testing
                with patch('stripe.PaymentIntent.create') as mock_create:
                    mock_pi = AsyncMock()
                    mock_pi.id = 'pi_test'
                    mock_pi.status = 'requires_payment_method'
                    mock_create.return_value = mock_pi
                    
                    result = await adapter.create_payment(
                        amount=Decimal('10.00'),
                        currency='USD',
                        customer_id='cust_test'
                    )
            else:
                result = await adapter.create_payment(
                    amount=Decimal('10.00'),
                    currency='USD'
                )
            
            # All should return dict with id and status
            assert isinstance(result, dict)
            assert 'id' in result
            assert 'status' in result
            assert isinstance(result['id'], str)
            assert isinstance(result['status'], str)