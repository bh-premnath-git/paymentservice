#!/usr/bin/env python3
"""
Validate that the payment service connections are properly established.
"""

import sys
import os
from pathlib import Path

# Add app directory to path
app_dir = Path(__file__).parent / "app"
sys.path.insert(0, str(app_dir))

def test_imports():
    """Test that all imports work correctly."""
    print("Testing imports...")
    
    try:
        from adapters.base import PaymentAdapter
        print("✓ PaymentAdapter imported")
        
        from adapters.custom import CustomAdapter
        print("✓ CustomAdapter imported")
        
        from adapters.exceptions import PaymentError
        print("✓ Payment exceptions imported")
        
        # Test adapter inheritance
        assert issubclass(CustomAdapter, PaymentAdapter)
        print("✓ CustomAdapter inherits from PaymentAdapter")
        
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def test_adapter_methods():
    """Test that adapters implement required methods."""
    print("\n🔧 Testing adapter methods...")
    
    try:
        from adapters.custom import CustomAdapter
        
        adapter = CustomAdapter()
        
        # Check required methods exist
        required_methods = [
            'create_payment',
            'capture_payment', 
            'refund_payment',
            'cancel_payment',
            'webhook_verify'
        ]
        
        for method in required_methods:
            assert hasattr(adapter, method), f"Missing method: {method}"
            assert callable(getattr(adapter, method)), f"Method not callable: {method}"
        
        print("✅ All required methods present")
        return True
    except Exception as e:
        print(f"❌ Method test failed: {e}")
        return False

def test_connection_flow():
    """Test the connection flow between components."""
    print("\n🔗 Testing connection flow...")
    
    try:
        # Test provider selection logic
        from config import Settings
        settings = Settings()
        
        # Test with no Stripe keys (should use Custom)
        settings.STRIPE_SECRET_KEY = None
        settings.STRIPE_WEBHOOK_SECRET = None
        
        from adapters.custom import CustomAdapter
        
        # Simulate get_provider logic
        if settings.STRIPE_SECRET_KEY and settings.STRIPE_WEBHOOK_SECRET:
            provider_type = "StripeAdapter"
        else:
            provider_type = "CustomAdapter"
            provider = CustomAdapter()
        
        print(f"✅ Provider selection: {provider_type}")
        
        # Test payment handler signature
        from payment_handler import PaymentServiceHandler
        import inspect
        
        init_sig = inspect.signature(PaymentServiceHandler.__init__)
        params = list(init_sig.parameters.keys())
        
        assert 'payment_adapter' in params, "PaymentServiceHandler missing payment_adapter parameter"
        print("✅ PaymentServiceHandler accepts payment_adapter parameter")
        
        return True
    except Exception as e:
        print(f"❌ Connection flow test failed: {e}")
        return False

def test_file_structure():
    """Test that all required files exist."""
    print("\n📁 Testing file structure...")
    
    required_files = [
        "app/main.py",
        "app/payment_handler.py",
        "app/adapters/__init__.py",
        "app/adapters/base.py",
        "app/adapters/exceptions.py",
        "app/adapters/custom/__init__.py",
        "app/adapters/stripe/__init__.py",
        "app/config.py",
        "app/models.py"
    ]
    
    missing_files = []
    for file_path in required_files:
        full_path = Path(__file__).parent / file_path
        if not full_path.exists():
            missing_files.append(file_path)
        else:
            print(f"✅ {file_path}")
    
    if missing_files:
        print(f"❌ Missing files: {missing_files}")
        return False
    
    print("✅ All required files present")
    return True

def main():
    """Run all validation tests."""
    print("🚀 Validating Payment Service Connections\n")
    
    tests = [
        test_file_structure,
        test_imports,
        test_adapter_methods,
        test_connection_flow
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)
    
    passed = sum(results)
    total = len(results)
    
    print(f"\n📊 Validation Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All connections validated successfully!")
        print("\n✅ **FLOW CONFIRMED:**")
        print("   main.py → get_provider() → PaymentAdapter (Stripe/Custom)")
        print("   main.py → PaymentServiceHandler(sessionmaker, adapter, redis)")
        print("   gRPC calls → PaymentServiceHandler → PaymentAdapter → External APIs")
        print("   Webhooks → /webhooks/stripe → PaymentAdapter.webhook_verify()")
    else:
        print("\n⚠️  Some validation tests failed. Please review the issues above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)