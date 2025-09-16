#!/usr/bin/env python3
"""
Test script to verify Stripe adapter integration.
Tests the Stripe adapter functionality and configuration.
"""

import os
import sys
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(ROOT_DIR)
sys.path.append(os.path.join(ROOT_DIR, "app"))

from adapters.stripe import StripeAdapter
from adapters.custom import CustomAdapter
from adapters.base import PaymentAdapter
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


class TestStripeConfiguration:
    """Test Stripe configuration and initialization."""
    
    def test_stripe_keys_format_validation(self):
        """Test that environment variables have correct Stripe key formats."""
        stripe_secret = os.getenv('STRIPE_SECRET_KEY')
        stripe_publishable = os.getenv('STRIPE_PUBLISHABLE_KEY')
        webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
        
        if stripe_secret:
            assert stripe_secret.startswith(('sk_test_', 'sk_live_')), \
                f"Invalid secret key format: {stripe_secret[:10]}..."
        
        if stripe_publishable:
            assert stripe_publishable.startswith(('pk_test_', 'pk_live_')), \
                f"Invalid publishable key format: {stripe_publishable[:10]}..."
        
        if webhook_secret:
            assert webhook_secret.startswith('whsec_'), \
                f"Invalid webhook secret format: {webhook_secret[:10]}..."

    def test_stripe_adapter_initialization(self):
        """Test Stripe adapter can be initialized with valid keys."""
        stripe_key = os.getenv('STRIPE_SECRET_KEY')
        webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
        
        if not stripe_key or not webhook_secret:
            pytest.skip("Stripe credentials not configured")
        
        adapter = StripeAdapter(
            api_key=stripe_key,
            webhook_secret=webhook_secret,
            enable_test_mode=True
        )
        
        assert adapter is not None
        assert adapter.webhook_secret == webhook_secret
        assert adapter.test_mode is True

    def test_stripe_adapter_without_credentials_fails(self):
        """Test that Stripe adapter fails without proper credentials."""
        with pytest.raises(Exception):
            StripeAdapter(
                api_key="",
                webhook_secret=""
            )


class TestCustomAdapter:
    """Test Custom adapter functionality."""
    
    @pytest.mark.asyncio
    async def test_custom_adapter_create_payment(self):
        """Test custom adapter payment creation."""
        adapter = CustomAdapter()
        
        result = await adapter.create_payment(
            amount=Decimal('10.00'),
            currency='USD'
        )
        
        assert result['id'] == 'custom_mock'
        assert result['amount'] == '10.00'
        assert result['currency'] == 'USD'
        assert result['status'] == 'created'

    @pytest.mark.asyncio
    async def test_custom_adapter_capture_payment(self):
        """Test custom adapter payment capture."""
        adapter = CustomAdapter()
        
        result = await adapter.capture_payment('test_payment_id')
        
        assert result['id'] == 'test_payment_id'
        assert result['status'] == 'captured'

    @pytest.mark.asyncio
    async def test_custom_adapter_refund_payment(self):
        """Test custom adapter payment refund."""
        adapter = CustomAdapter()
        
        result = await adapter.refund_payment('test_payment_id')
        
        assert result['id'] == 'test_payment_id'
        assert result['status'] == 'refunded'

    @pytest.mark.asyncio
    async def test_custom_adapter_cancel_payment(self):
        """Test custom adapter payment cancellation."""
        adapter = CustomAdapter()
        
        result = await adapter.cancel_payment('test_payment_id')
        
        assert result['id'] == 'test_payment_id'
        assert result['status'] == 'cancelled'

    @pytest.mark.asyncio
    async def test_custom_adapter_webhook_verify(self):
        """Test custom adapter webhook verification."""
        adapter = CustomAdapter()
        
        payload = b'{"type": "payment.succeeded", "data": {"id": "test_123"}}'
        result = await adapter.webhook_verify(payload, "test_signature")
        
        assert result['type'] == 'payment.succeeded'
        assert result['data']['id'] == 'test_123'


class TestAdapterArchitecture:
    """Test that adapter architecture supports multiple providers."""
    
    def test_stripe_adapter_inherits_from_base(self):
        """Test StripeAdapter properly inherits from PaymentAdapter."""
        assert issubclass(StripeAdapter, PaymentAdapter)

    def test_custom_adapter_inherits_from_base(self):
        """Test CustomAdapter properly inherits from PaymentAdapter."""
        assert issubclass(CustomAdapter, PaymentAdapter)

    def test_adapters_implement_required_methods(self):
        """Test that all adapters implement required PaymentAdapter interface."""
        required_methods = [
            'create_payment',
            'capture_payment',
            'refund_payment', 
            'cancel_payment',
            'webhook_verify'
        ]
        
        for method in required_methods:
            assert hasattr(StripeAdapter, method), f"StripeAdapter missing {method}"
            assert hasattr(CustomAdapter, method), f"CustomAdapter missing {method}"

    def test_exception_hierarchy(self):
        """Test that payment exceptions are properly defined."""
        exceptions = [
            PaymentError,
            ValidationError,
            InsufficientFundsError,
            PaymentNotFoundError,
            PaymentProcessingError,
            RefundError,
            WebhookError,
            RateLimitError,
            AuthenticationError
        ]
        
        for exc in exceptions[1:]:  # Skip base PaymentError
            assert issubclass(exc, PaymentError), f"{exc.__name__} should inherit from PaymentError"


class TestProviderSelection:
    """Test provider selection logic."""
    
    @patch.dict(os.environ, {
        'STRIPE_SECRET_KEY': 'sk_test_123',
        'STRIPE_WEBHOOK_SECRET': 'whsec_123'
    })
    def test_provider_selection_with_stripe_credentials(self):
        """Test provider selection chooses Stripe when credentials available."""
        # Import here to avoid circular imports in main module
        from main import get_provider
        
        # Clear the cache
        get_provider.cache_clear()
        
        provider = get_provider()
        assert isinstance(provider, StripeAdapter)

    @patch.dict(os.environ, {
        'STRIPE_SECRET_KEY': '',
        'STRIPE_WEBHOOK_SECRET': ''
    }, clear=True)
    def test_provider_selection_without_stripe_credentials(self):
        """Test provider selection falls back to Custom when no Stripe credentials."""
        from main import get_provider
        
        # Clear the cache
        get_provider.cache_clear()
        
        provider = get_provider()
        assert isinstance(provider, CustomAdapter)


class TestStripeAdapterMethods:
    """Test Stripe adapter specific methods (mocked)."""
    
    @pytest.mark.asyncio
    async def test_stripe_create_customer(self):
        """Test Stripe customer creation (mocked)."""
        stripe_key = os.getenv('STRIPE_SECRET_KEY')
        webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
        
        if not stripe_key or not webhook_secret:
            pytest.skip("Stripe credentials not configured")
        
        adapter = StripeAdapter(
            api_key=stripe_key,
            webhook_secret=webhook_secret,
            enable_test_mode=True
        )
        
        # Mock Stripe API calls to avoid actual API requests
        with patch('stripe.Customer.list') as mock_list, \
             patch('stripe.Customer.create') as mock_create:
            
            mock_list.return_value.data = []
            mock_create.return_value.to_dict.return_value = {
                'id': 'cus_test123',
                'email': 'test@example.com'
            }
            
            result = await adapter.create_or_update_customer(
                user_id='user123',
                email='test@example.com',
                name='Test User'
            )
            
            assert result['id'] == 'cus_test123'
            assert result['email'] == 'test@example.com'

    @pytest.mark.asyncio
    async def test_stripe_webhook_verification_mock(self):
        """Test Stripe webhook verification with mock."""
        stripe_key = os.getenv('STRIPE_SECRET_KEY')
        webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
        
        if not stripe_key or not webhook_secret:
            pytest.skip("Stripe credentials not configured")
        
        adapter = StripeAdapter(
            api_key=stripe_key,
            webhook_secret=webhook_secret,
            enable_test_mode=True
        )
        
        # Mock webhook event
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
                    'status': 'succeeded'
                }
            }
        }
        
        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = mock_event
            
            result = await adapter.webhook_verify(
                payload=b'{"test": "data"}',
                sig_header='test_signature'
            )
            
            assert result['id'] == 'evt_test123'
            assert result['type'] == 'payment_intent.succeeded'
            assert result['data']['id'] == 'pi_test123'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])