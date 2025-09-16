"""
Pytest configuration and fixtures for payment service tests.
"""

import os
import sys
import pytest
from unittest.mock import AsyncMock

# Add app directory to Python path for imports
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(ROOT_DIR)
sys.path.append(os.path.join(ROOT_DIR, "app"))


@pytest.fixture(scope="session")
def test_env():
    """Fixture to set up test environment variables."""
    # Ensure we're using test Stripe keys if available
    test_env_vars = {
        'ENVIRONMENT': 'test',
        'LOG_LEVEL': 'DEBUG',
        'DATABASE_URL': 'sqlite+aiosqlite:///:memory:',
        'REDIS_URL': 'redis://localhost:6379/1',  # Use test DB
    }
    
    # Set test environment variables
    for key, value in test_env_vars.items():
        os.environ.setdefault(key, value)
    
    return test_env_vars


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis_mock = AsyncMock()
    redis_mock.ping.return_value = True
    redis_mock.get.return_value = None
    redis_mock.setex.return_value = True
    redis_mock.close.return_value = None
    return redis_mock


@pytest.fixture
def mock_stripe_client():
    """Mock Stripe client for testing."""
    import stripe
    from unittest.mock import MagicMock
    
    # Mock common Stripe objects
    mock_customer = MagicMock()
    mock_customer.id = "cus_test123"
    mock_customer.email = "test@example.com"
    mock_customer.to_dict.return_value = {
        "id": "cus_test123",
        "email": "test@example.com"
    }
    
    mock_payment_intent = MagicMock()
    mock_payment_intent.id = "pi_test123"
    mock_payment_intent.client_secret = "pi_test123_secret"
    mock_payment_intent.amount = 1000
    mock_payment_intent.currency = "usd"
    mock_payment_intent.status = "succeeded"
    mock_payment_intent.created = 1234567890
    mock_payment_intent.metadata = {}
    
    # Mock Stripe API methods
    stripe.Customer.create = MagicMock(return_value=mock_customer)
    stripe.Customer.list = MagicMock(return_value=MagicMock(data=[]))
    stripe.PaymentIntent.create = MagicMock(return_value=mock_payment_intent)
    stripe.PaymentIntent.retrieve = MagicMock(return_value=mock_payment_intent)
    
    return {
        'customer': mock_customer,
        'payment_intent': mock_payment_intent
    }


@pytest.fixture
def stripe_test_keys():
    """Provide test Stripe keys if available."""
    return {
        'secret_key': os.getenv('STRIPE_SECRET_KEY', 'sk_test_fake'),
        'publishable_key': os.getenv('STRIPE_PUBLISHABLE_KEY', 'pk_test_fake'),
        'webhook_secret': os.getenv('STRIPE_WEBHOOK_SECRET', 'whsec_fake')
    }


# Configure pytest-asyncio
def pytest_configure(config):
    """Configure pytest with asyncio support."""
    config.addinivalue_line("markers", "asyncio: mark test as async")


# Test collection configuration
def pytest_collection_modifyitems(config, items):
    """Add asyncio marker to async test functions."""
    for item in items:
        if "asyncio" in item.keywords:
            item.add_marker(pytest.mark.asyncio)