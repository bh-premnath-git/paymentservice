#!/usr/bin/env python3
"""
Simple test script to test the payment service gRPC API
"""
import grpc
import sys
import os
import json
from datetime import datetime

# Add the payment protobuf modules to path
sys.path.append('/workspace/payment')

try:
    from payment.v1 import payment_pb2, payment_pb2_grpc
    print("✅ Successfully imported protobuf modules")
except ImportError as e:
    print(f"❌ Failed to import protobuf modules: {e}")
    print("Trying alternative import path...")
    try:
        # Try importing from current directory
        import payment_pb2, payment_pb2_grpc
        print("✅ Successfully imported protobuf modules from current directory")
    except ImportError as e2:
        print(f"❌ Failed to import from current directory: {e2}")
        print("Please ensure the protobuf files are generated and accessible")
        sys.exit(1)

def test_payment_service():
    """Test the payment service gRPC API"""
    print("🔍 Testing Payment Service gRPC API...")
    
    # Connect to gRPC server
    channel = grpc.insecure_channel('localhost:50051')
    stub = payment_pb2_grpc.PaymentServiceStub(channel)
    
    try:
        # Test 1: Create a payment
        print("\n📝 Test 1: Creating a payment...")
        
        create_request = payment_pb2.CreatePaymentRequest(
            amount=10050,  # $100.50 in cents
            currency="USD",
            customer_id="test-customer-123",
            payment_method="credit_card",
            metadata=json.dumps({"order_id": "order-456", "test": True})
        )
        
        response = stub.CreatePayment(create_request)
        print(f"✅ Payment created successfully!")
        print(f"   Payment ID: {response.payment_id}")
        print(f"   Status: {response.status}")
        print(f"   Amount: ${response.amount/100:.2f} {response.currency}")
        
        payment_id = response.payment_id
        
        # Test 2: Get the payment
        print(f"\n🔍 Test 2: Retrieving payment {payment_id}...")
        
        get_request = payment_pb2.GetPaymentRequest(payment_id=payment_id)
        response = stub.GetPayment(get_request)
        
        print(f"✅ Payment retrieved successfully!")
        print(f"   Payment ID: {response.payment_id}")
        print(f"   Status: {response.status}")
        print(f"   Amount: ${response.amount/100:.2f} {response.currency}")
        print(f"   Customer: {response.customer_id}")
        print(f"   Created: {response.created_at}")
        
        # Test 3: List payments
        print(f"\n📋 Test 3: Listing payments...")
        
        list_request = payment_pb2.ListPaymentsRequest(
            customer_id="test-customer-123",
            limit=10
        )
        response = stub.ListPayments(list_request)
        
        print(f"✅ Found {len(response.payments)} payments for customer")
        for payment in response.payments:
            print(f"   - {payment.payment_id}: ${payment.amount/100:.2f} {payment.currency} ({payment.status})")
        
        # Test 4: Process the payment
        print(f"\n⚡ Test 4: Processing payment {payment_id}...")
        
        process_request = payment_pb2.ProcessPaymentRequest(
            payment_id=payment_id
        )
        response = stub.ProcessPayment(process_request)
        
        print(f"✅ Payment processing initiated!")
        print(f"   Payment ID: {response.payment_id}")
        print(f"   Status: {response.status}")
        
        print(f"\n🎉 All tests completed successfully!")
        
    except grpc.RpcError as e:
        print(f"❌ gRPC Error: {e.details()}")
        print(f"   Code: {e.code()}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        channel.close()
    
    return True

if __name__ == "__main__":
    print("🚀 Starting Payment Service Tests...")
    print("=" * 50)
    
    success = test_payment_service()
    
    print("=" * 50)
    if success:
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed!")
        sys.exit(1)