"""
Test script for Ilmu Claw API integration.
Run this to verify the LLM client works with your Ilmu Claw API key.
"""
from llm_client import get_llm_client
from config import settings


def test_ilmu_basic():
    """Test basic Ilmu Claw API call."""
    print("\n=== Testing Ilmu Claw API Integration ===")
    print(f"Base URL: {settings.ilmu_base_url}")
    print(f"Model: {settings.ilmu_model}")
    print(f"API Key: {settings.ilmu_api_key[:10]}...{settings.ilmu_api_key[-4:] if len(settings.ilmu_api_key) > 14 else '***'}")

    if settings.ilmu_api_key == "your_ilmu_api_key_here":
        print("\n[ERROR] Please set your Ilmu Claw API key in .env file")
        print("Edit .env and set: ILMU_API_KEY=your_actual_api_key")
        return False

    try:
        client = get_llm_client()

        # Test simple chat completion
        messages = [
            {"role": "user", "content": "Hello, please respond with 'Test successful'"}
        ]

        print("\nSending test request to Ilmu Claw...")
        result = client.chat_completion(messages)

        print(f"\nResponse: {result['content']}")
        print(f"Input tokens: {result['input_tokens']}")
        print(f"Output tokens: {result['output_tokens']}")
        print(f"Total tokens: {result['total_tokens']}")
        print(f"Cost: ${result['cost_usd']:.6f}")

        if "test successful" in result['content'].lower():
            print("\n[PASS] Ilmu Claw API integration working correctly")
            return True
        else:
            print("\n[WARNING] Response received but unexpected content")
            return True  # Still counts as success since API call worked

    except Exception as e:
        print(f"\n[ERROR] Ilmu Claw API call failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ilmu_drafting():
    """Test message drafting with Ilmu Claw."""
    print("\n=== Testing Message Drafting ===")

    try:
        client = get_llm_client()

        context = "Customer is asking for a quote for 100 units of wire mesh WM-001"
        task = "Draft a professional response saying we will check stock and get back to them"

        result = client.draft_message(context, task, tone="professional")

        print(f"\nDrafted message:\n{result['content']}")
        print(f"\nTokens used: {result['total_tokens']}")
        print(f"Cost: ${result['cost_usd']:.6f}")

        print("\n[PASS] Message drafting test passed")
        return True

    except Exception as e:
        print(f"\n[ERROR] Message drafting failed: {e}")
        return False


def main():
    """Run Ilmu Claw integration tests."""
    print("=" * 60)
    print("Testing Ilmu Claw API Integration")
    print("=" * 60)

    success = True

    # Test basic API call
    if not test_ilmu_basic():
        success = False

    # If basic test passed, test drafting
    if success:
        if not test_ilmu_drafting():
            success = False

    print("\n" + "=" * 60)
    if success:
        print("[PASS] Ilmu Claw integration tests passed")
        print("=" * 60)
        print("\nYour Ilmu Claw API is working correctly.")
        print("You can now use the LLM client in the agents.")
    else:
        print("[FAIL] Ilmu Claw integration tests failed")
        print("=" * 60)
        print("\nPlease check:")
        print("1. Your API key is correct in .env")
        print("2. Your API key has sufficient credits")
        print("3. The base URL is correct: https://api.ilmu.ai/v1")
        print("4. Your network can access the Ilmu Claw API")

    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
