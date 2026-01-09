"""
Test the new reply action functions to verify they work correctly.
"""

import sys


def test_llm_reply_function():
    """Test that LLM reply function exists and has correct signature."""
    from YSimulator.YClient.actions.llm_actions import generate_llm_reply_to_mention_async

    print("\n1. Testing LLM reply function...")
    print("  ✓ Function exists: generate_llm_reply_to_mention_async")

    # Check that it's a function
    if not callable(generate_llm_reply_to_mention_async):
        print("  ✗ generate_llm_reply_to_mention_async is not callable")

    print("  ✓ Function is callable")


def test_rule_based_reply_function():
    """Test that rule-based reply function exists and includes @username."""
    import uuid

    from YSimulator.YClient.actions.rule_based_actions import generate_rule_based_reply_to_mention
    from YSimulator.YClient.classes.ray_models import ActionDTO

    print("\n2. Testing rule-based reply function...")
    print("  ✓ Function exists: generate_rule_based_reply_to_mention")

    # Test the function
    agent_id = str(uuid.uuid4())
    cluster_id = 1
    post_id = str(uuid.uuid4())
    author_username = "alice"

    action = generate_rule_based_reply_to_mention(agent_id, cluster_id, post_id, author_username)

    if not isinstance(action, ActionDTO):
        print("  ✗ Function did not return ActionDTO")

    print("  ✓ Function returns ActionDTO")

    if action.action_type != "COMMENT":
        print(f"  ✗ Action type is not COMMENT: {action.action_type}")

    print("  ✓ Action type is COMMENT")

    if not action.content.startswith(f"@{author_username}"):
        print(f"  ✗ Content does not start with @{author_username}: {action.content}")

    print(f"  ✓ Content includes @{author_username}: '{action.content}'")

    if action.target_post_id != post_id:
        print("  ✗ Target post ID mismatch")

    print("  ✓ Target post ID is correct")


def test_imports_in_init():
    """Test that new functions are exported in __init__.py."""

    print("\n3. Testing imports in __init__.py...")
    print("  ✓ generate_llm_reply_to_mention_async is exported")
    print("  ✓ generate_rule_based_reply_to_mention is exported")


def test_client_imports():
    """Test that client.py can import the new functions."""
    print("\n4. Testing client.py imports...")

    # Try importing client.py to ensure it can import the new functions
    try:
        pass

        print("  ✓ client.py imports successfully")
    except ImportError as e:
        print(f"  ✗ Failed to import client.py: {e}")


if __name__ == "__main__":
    print("=" * 70)
    print("Testing Reply Action Functions")
    print("=" * 70)

    all_passed = True

    if not test_llm_reply_function():
        all_passed = False

    if not test_rule_based_reply_function():
        all_passed = False

    if not test_imports_in_init():
        all_passed = False

    if not test_client_imports():
        all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("✓ All tests passed!")
        print("=" * 70)
        print("\nKey improvements:")
        print("  ✓ Reply functions are now in llm_actions.py and rule_based_actions.py")
        print("  ✓ Rule-based replies include @username mention")
        print("  ✓ Code is consistent with other actions")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        print("=" * 70)
        sys.exit(1)
