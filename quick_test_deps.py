import asyncio
import requests
import sys

async def test_external_services():
    """Quick test of external services"""
    print("🔍 Testing external dependencies...\n")
    
    success = True
    
    # Test PostgreSQL (simple connection test)
    print("Testing PostgreSQL connection...")
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="payment",
            password="payment",
            database="payment_db"
        )
        result = await conn.fetchval("SELECT 1;")
        await conn.close()
        print("✓ PostgreSQL connected successfully!")
    except Exception as e:
        print(f"✗ PostgreSQL connection failed: {e}")
        success = False
    
    # Test Redis
    print("\nTesting Redis connection...")
    try:
        import redis
        r = redis.from_url("redis://localhost:6379/0")
        r.ping()
        print("✓ Redis connected successfully!")
    except Exception as e:
        print(f"✗ Redis connection failed: {e}")
        success = False
    
    # Test Keycloak
    print("\nTesting Keycloak connection...")
    try:
        response = requests.get("http://localhost:8080/health", timeout=5)
        if response.status_code == 200:
            print("✓ Keycloak health endpoint accessible")
        else:
            print(f"⚠ Keycloak returned status: {response.status_code}")
    except Exception as e:
        print(f"✗ Keycloak connection failed: {e}")
        success = False
    
    return success

if __name__ == "__main__":
    result = asyncio.run(test_external_services())
    if result:
        print("\n✅ All external dependencies are accessible!")
        sys.exit(0)
    else:
        print("\n❌ Some external dependencies failed. Please fix them before running the payment service.")
        sys.exit(1)