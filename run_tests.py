#!/usr/bin/env python3
"""
Test runner script for the payment service.
Runs all tests in the tests/ directory with proper configuration.
"""

import os
import sys
import subprocess
from pathlib import Path

def main():
    """Run all tests with pytest."""
    # Get the project root directory
    project_root = Path(__file__).parent
    
    # Add app directory to Python path
    app_dir = project_root / "app"
    sys.path.insert(0, str(app_dir))
    sys.path.insert(0, str(project_root))
    
    # Set environment variables for testing
    test_env = os.environ.copy()
    test_env.update({
        'ENVIRONMENT': 'test',
        'LOG_LEVEL': 'WARNING',  # Reduce log noise during testing
        'DATABASE_URL': 'sqlite+aiosqlite:///:memory:',
        'REDIS_URL': 'redis://localhost:6379/1',  # Use test DB
    })
    
    # Pytest command with options
    pytest_args = [
        sys.executable, '-m', 'pytest',
        'tests/',
        '-v',                    # Verbose output
        '--tb=short',            # Short traceback format
        '--asyncio-mode=auto',   # Auto async mode
        '--capture=no',          # Don't capture output (for debugging)
        '--durations=10',        # Show 10 slowest tests
    ]
    
    # Add coverage if available
    try:
        import pytest_cov
        pytest_args.extend([
            '--cov=app',
            '--cov-report=term-missing',
            '--cov-report=html:htmlcov',
        ])
        print("📊 Running tests with coverage analysis...")
    except ImportError:
        print("📋 Running tests without coverage (install pytest-cov for coverage)")
    
    # Run specific test types based on command line args
    if len(sys.argv) > 1:
        test_type = sys.argv[1].lower()
        
        if test_type == 'stripe':
            pytest_args.append('tests/test_stripe_integration.py')
            print("🔧 Running Stripe integration tests only...")
        elif test_type == 'adapters':
            pytest_args.append('tests/test_adapters.py')
            print("🔧 Running adapter tests only...")
        elif test_type == 'unit':
            pytest_args.extend([
                'tests/test_adapters.py',
                'tests/test_list_payments.py',
                'tests/test_metadata_persistence.py'
            ])
            print("🔧 Running unit tests only...")
        elif test_type == 'integration':
            pytest_args.extend([
                'tests/test_stripe_integration.py',
                'tests/test_reflection_enabled.py',
                'tests/test_requestor_mock_metadata.py'
            ])
            print("🔧 Running integration tests only...")
        else:
            print(f"❌ Unknown test type: {test_type}")
            print("Available types: stripe, adapters, unit, integration")
            return 1
    else:
        print("🚀 Running all tests...")
    
    # Check if required dependencies are available
    try:
        import pytest
        import pytest_asyncio
    except ImportError as e:
        print(f"❌ Missing required test dependency: {e}")
        print("Install with: pip install pytest pytest-asyncio")
        return 1
    
    # Run the tests
    try:
        result = subprocess.run(
            pytest_args,
            env=test_env,
            cwd=project_root,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            print("\n✅ All tests passed!")
        else:
            print(f"\n❌ Tests failed with exit code: {result.returncode}")
        
        return result.returncode
        
    except subprocess.TimeoutExpired:
        print("\n⏰ Tests timed out after 5 minutes")
        return 1
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Error running tests: {e}")
        return 1


if __name__ == "__main__":
    exit(main())