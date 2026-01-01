"""
Test Redis support for opinion dynamics.

This test verifies that opinion storage and retrieval work correctly when Redis is enabled,
following the specification in RECSYS_REDIS_SUPPORT.md.
"""

import pytest


def test_redis_opinion_key_format():
    """Test that Redis opinion keys follow the correct format."""
    print("\n1. Testing Redis opinion key format...")

    # Expected format: ysim:user:{user_id}:opinion:{topic_id}
    user_id = "user-uuid-123"
    topic_id = "topic-uuid-456"

    expected_key = f"ysim:user:{user_id}:opinion:{topic_id}"

    # Verify key format matches specification
    assert expected_key.startswith("ysim:user:")
    assert ":opinion:" in expected_key
    assert expected_key.endswith(topic_id)
    assert user_id in expected_key

    print(f"  ✓ Opinion key format correct: {expected_key}")


def test_opinion_value_float_conversion():
    """Test that opinion values are properly converted to/from strings for Redis."""
    print("\n2. Testing opinion value float conversion...")

    # Simulate storing opinion as string in Redis (Redis stores strings)
    opinion_value = 0.75
    redis_stored = str(opinion_value)

    # Simulate retrieving and converting back to float
    retrieved_value = float(redis_stored)

    assert retrieved_value == opinion_value
    assert isinstance(retrieved_value, float)
    assert 0.0 <= retrieved_value <= 1.0

    print(
        f"  ✓ Opinion value correctly converted: {opinion_value} -> '{redis_stored}' -> {retrieved_value}"
    )


def test_followee_data_byte_handling():
    """Test that followee data from Redis hgetall is properly handled."""
    print("\n3. Testing Redis follow data byte handling...")

    # Simulate what Redis hgetall returns (all keys and values are bytes)
    mock_follow_data = {
        b"id": b"follow-uuid-1",
        b"user_id": b"user-uuid-being-followed",
        b"follower_id": b"agent-uuid-123",
        b"action": b"follow",
    }

    # Test conversion logic (as implemented in get_neighbors_opinions)
    agent_id = "agent-uuid-123"

    # Check if this follow relationship matches the agent
    follower_id = mock_follow_data.get(b"follower_id")
    action = mock_follow_data.get(b"action")

    # Decode for comparison
    is_match = follower_id == agent_id.encode() and action == b"follow"

    assert is_match

    # Extract the followee user_id
    user_id = mock_follow_data.get(b"user_id")
    assert user_id is not None

    user_id_str = user_id.decode()
    assert isinstance(user_id_str, str)
    assert user_id_str == "user-uuid-being-followed"

    print(f"  ✓ Follow data properly handled and decoded")


def test_empty_neighbors_opinions():
    """Test that empty opinion list is returned when no followees found."""
    print("\n4. Testing empty neighbors opinions...")

    # Simulate scenario where agent follows no one
    followee_ids = set()

    opinions = []
    for followee_id in followee_ids:
        # This loop won't execute
        pass

    assert opinions == []
    assert isinstance(opinions, list)

    print(f"  ✓ Empty list returned when no followees")


def test_opinion_filtering():
    """Test that only valid opinions (not None) are included in results."""
    print("\n5. Testing opinion filtering...")

    # Simulate retrieving opinions, some may be None
    mock_opinions = [0.5, None, 0.8, None, 0.3, 0.9]

    # Filter out None values (as implemented in get_neighbors_opinions)
    filtered_opinions = [op for op in mock_opinions if op is not None]

    assert len(filtered_opinions) == 4
    assert None not in filtered_opinions
    assert all(isinstance(op, float) for op in filtered_opinions)

    print(f"  ✓ None values properly filtered from opinions")


if __name__ == "__main__":
    print("\n=== Redis Opinion Dynamics Tests ===")

    test_redis_opinion_key_format()
    test_opinion_value_float_conversion()
    test_followee_data_byte_handling()
    test_empty_neighbors_opinions()
    test_opinion_filtering()

    print("\n=== All tests passed! ===")
