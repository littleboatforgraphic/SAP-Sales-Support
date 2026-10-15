"""
Test script for email PO processing.

This script tests the email webhook with mock PO emails.
"""

import requests
import json

# Configuration
BASE_URL = "http://localhost:8000"
WEBHOOK_URL = f"{BASE_URL}/api/v1/webhook/email-po/mock"
EMAIL_SECRET = "test_secret_token"  # Set this in .env as EMAIL_WEBHOOK_SECRET_TOKEN


def test_mock_email_po():
    """Test the mock email PO endpoint."""
    print("Testing Email PO Processing with Mock Data")
    print("=" * 60)
    
    try:
        # Call the mock endpoint
        response = requests.post(
            WEBHOOK_URL,
            headers={
                "Content-Type": "application/json",
                "X-Email-Secret-Token": EMAIL_SECRET
            },
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"\nResponse:")
            print(json.dumps(result, indent=2))
            
            if result.get("status") == "success":
                print(f"\n✅ Successfully processed {result.get('processed_count', 0)} PO emails")
                
                for email_result in result.get("results", []):
                    print(f"\nEmail ID: {email_result.get('email_id')}")
                    print(f"Sender: {email_result.get('sender')}")
                    print(f"Subject: {email_result.get('subject')}")
                    print(f"Agent Response: {email_result.get('agent_response', '')[:100]}...")
            else:
                print(f"\n❌ No PO emails found")
        else:
            print(f"\n❌ Error: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Connection Error: Could not connect to {BASE_URL}")
        print("Make sure the server is running: python main.py")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")


def test_real_email_po():
    """Test with a real email PO payload."""
    print("\n\nTesting with Real Email PO Payload")
    print("=" * 60)
    
    # Replace with your real customer email address
    real_email = input("Enter customer email address (or press Enter to use default): ").strip()
    if not real_email:
        real_email = "customer@realcompany.com"
    
    payload = {
        "sender": real_email,
        "subject": "PO-2026-001 - Wire Mesh Order",
        "body": "Please find attached our purchase order for wire mesh products.",
        "attachment": {
            "filename": "PO-2026-001.pdf",
            "content": "base64_encoded_pdf_content_here"
        },
        "received_at": "2026-10-12T10:00:00Z"
    }
    
    print(f"\nTesting with email: {real_email}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/webhook/email-po",
            headers={
                "Content-Type": "application/json",
                "X-Email-Secret-Token": EMAIL_SECRET
            },
            json=payload,
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"\nResponse:")
            print(json.dumps(result, indent=2))
        else:
            print(f"\n❌ Error: {response.text}")
            
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")


if __name__ == "__main__":
    print("Email PO Processing Test")
    print("=" * 60)
    print(f"Server URL: {BASE_URL}")
    print(f"Email Secret: {EMAIL_SECRET}")
    print()
    
    # Test with mock data
    test_mock_email_po()
    
    # Test with real payload
    print("\n\nPress Enter to test with real email payload, or Ctrl+C to exit...")
    input()
    test_real_email_po()
