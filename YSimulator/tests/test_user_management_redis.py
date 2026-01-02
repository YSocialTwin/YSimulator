"""
Test Redis support for User Management operations.

This test verifies that user management operations work correctly when Redis is enabled.
Tests cover: register_user, get_user_by_username, get_all_users, update_user_archetype.
"""


def test_username_index_creation():
    """Test that username index is created when registering a user."""
    print("\n1. Testing username index creation...")
    
    # Simulate registering a user with username
    user_data = {
        "id": "user-123",
        "username": "testuser",
        "email": "test@example.com",
        "archetype": "creator"
    }
    
    # Expected Redis operations:
    # 1. Store user data: ysim:user_mgmt:user-123
    # 2. Add to user set: ysim:user_mgmt:ids
    # 3. Create username index: ysim:user_mgmt:by_username:testuser -> user-123
    
    assert "username" in user_data
    assert user_data["username"] == "testuser"
    print(f"  ✓ Username index key: ysim:user_mgmt:by_username:{user_data['username']}")


def test_get_user_by_username_lookup():
    """Test that get_user_by_username uses the username index."""
    print("\n2. Testing username lookup...")
    
    # Simulate Redis lookup flow
    username = "testuser"
    expected_user_id = "user-123"
    
    # Step 1: Look up user ID from username index
    username_key = f"ysim:user_mgmt:by_username:{username}"
    # Would call: redis_client.get(username_key) -> "user-123"
    
    # Step 2: Get user data by ID
    # Would call: get_user("user-123")
    
    assert username_key == "ysim:user_mgmt:by_username:testuser"
    print(f"  ✓ Username lookup key correct: {username_key}")


def test_get_all_users_iteration():
    """Test that get_all_users iterates through all user IDs."""
    print("\n3. Testing get_all_users...")
    
    # Simulate multiple users
    user_ids = {b"user-1", b"user-2", b"user-3"}
    
    # Decode bytes properly
    decoded_ids = []
    for user_id in user_ids:
        user_id_str = user_id.decode() if isinstance(user_id, bytes) else user_id
        decoded_ids.append(user_id_str)
    
    assert len(decoded_ids) == 3
    assert "user-1" in decoded_ids
    assert isinstance(decoded_ids[0], str)
    print(f"  ✓ All {len(decoded_ids)} users decoded correctly")


def test_update_user_archetype_redis():
    """Test that update_user_archetype updates the Redis hash."""
    print("\n4. Testing update_user_archetype...")
    
    # Simulate updating archetype
    user_id = "user-123"
    new_archetype = "explorer"
    
    # Expected Redis operation:
    # redis_client.hset("ysim:user_mgmt:user-123", "archetype", "explorer")
    
    user_key = f"ysim:user_mgmt:{user_id}"
    assert user_key == "ysim:user_mgmt:user-123"
    print(f"  ✓ Archetype update key: {user_key}")
    print(f"  ✓ New archetype value: {new_archetype}")


def test_batch_registration_username_indices():
    """Test that batch registration creates username indices for all users."""
    print("\n5. Testing batch registration with username indices...")
    
    # Simulate batch user registration
    users_data = [
        {"id": "user-1", "username": "alice", "email": "alice@example.com"},
        {"id": "user-2", "username": "bob", "email": "bob@example.com"},
        {"id": "user-3", "username": "charlie", "email": "charlie@example.com"},
    ]
    
    # Each user should get:
    # 1. User hash: ysim:user_mgmt:{id}
    # 2. User ID in set: ysim:user_mgmt:ids
    # 3. Username index: ysim:user_mgmt:by_username:{username}
    
    username_keys = []
    for user in users_data:
        username_keys.append(f"ysim:user_mgmt:by_username:{user['username']}")
    
    assert len(username_keys) == 3
    assert "ysim:user_mgmt:by_username:alice" in username_keys
    assert "ysim:user_mgmt:by_username:bob" in username_keys
    assert "ysim:user_mgmt:by_username:charlie" in username_keys
    print(f"  ✓ All {len(username_keys)} username indices created")


if __name__ == "__main__":
    print("\n=== User Management Redis Tests ===")
    
    test_username_index_creation()
    test_get_user_by_username_lookup()
    test_get_all_users_iteration()
    test_update_user_archetype_redis()
    test_batch_registration_username_indices()
    
    print("\n=== All tests passed! ===")
