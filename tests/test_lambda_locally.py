#!/usr/bin/env python3
"""Test Lambda function locally before deployment"""

import json
import sys
import os
import pytest

pytestmark = pytest.mark.integration

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_lambda_handler():
    """Test the Lambda handler locally"""
    from src.lambda.handler import lambda_handler
    
    # Test event
    test_event = {
        "accounts": {
            "test-account": {
                "account_id": "123456789012",
                "role_name": "InventoryRole"
            }
        }
    }
    
    # Mock context
    class Context:
        function_name = "test-function"
        memory_limit_in_mb = 512
        invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test"
        aws_request_id = "test-request-id"
    
    print("Testing Lambda handler locally...")
    print(f"Event: {json.dumps(test_event, indent=2)}")
    
    try:
        # Set environment variables
        os.environ['DYNAMODB_TABLE_NAME'] = 'test-inventory-table'
        
        # Call handler
        result = lambda_handler(test_event, Context())
        
        print(f"\nResult: {json.dumps(result, indent=2)}")
        
        if result['statusCode'] == 200:
            print("\n✅ Lambda handler test passed!")
        else:
            print("\n❌ Lambda handler test failed!")
            
    except Exception as e:
        print(f"\n❌ Error testing Lambda: {str(e)}")
        import traceback
        traceback.print_exc()

def test_collector_import():
    """Test that collector can be imported"""
    try:
        from src.collector.main import AWSInventoryCollector
        print("✅ Collector module imported successfully")
        
        # Test instantiation
        collector = AWSInventoryCollector('test-table')
        print("✅ Collector instantiated successfully")
        
    except Exception as e:
        print(f"❌ Error importing collector: {str(e)}")

def check_dependencies():
    """Check that all required dependencies are available"""
    required_modules = [
        'boto3',
        'botocore',
        'click',
        'tabulate',
        'dateutil',
        'jmespath',
        'yaml'
    ]
    
    print("Checking dependencies...")
    all_good = True
    
    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ {module}")
        except ImportError:
            print(f"❌ {module} - Not installed")
            all_good = False
    
    return all_good

def main():
    """Run all tests"""
    print("AWS Inventory Lambda Local Test")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        print("\n⚠️  Missing dependencies. Run: pip install -r requirements.txt")
        sys.exit(1)
    
    print("\n" + "=" * 50)
    
    # Test imports
    test_collector_import()
    
    print("\n" + "=" * 50)
    
    # Test Lambda handler
    test_lambda_handler()
    
    print("\n" + "=" * 50)
    print("Local testing complete!")

if __name__ == "__main__":
    main()