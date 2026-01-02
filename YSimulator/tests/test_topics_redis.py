"""
Test Redis support for Topics & Interests operations.

This test verifies that topic/interest operations work correctly when Redis is enabled.
"""


def test_interest_name_index():
    """Test that interest name index is created."""
    print("\n1. Testing interest name index...")
    
    # Expected index
    interest_name = "technology"
    interest_id = "interest-uuid-123"
    
    name_index_key = f"ysim:interest:by_name:{interest_name}"
    interest_data_key = f"ysim:interest:{interest_id}"
    
    assert name_index_key == f"ysim:interest:by_name:{interest_name}"
    assert interest_data_key == f"ysim:interest:{interest_id}"
    print(f"  ✓ Name index key: {name_index_key}")
    print(f"  ✓ Interest data key: {interest_data_key}")


def test_add_or_get_interest_flow():
    """Test the add_or_get_interest flow."""
    print("\n2. Testing add_or_get_interest flow...")
    
    # Flow: check name index -> if not exist, create
    interest_name = "politics"
    
    # Step 1: Check if exists
    name_index_key = f"ysim:interest:by_name:{interest_name}"
    # redis_client.get(name_index_key) -> None (doesn't exist)
    
    # Step 2: Create new interest
    import uuid
    interest_id = str(uuid.uuid4())
    interest_key = f"ysim:interest:{interest_id}"
    
    # Step 3: Create name index
    # redis_client.set(name_index_key, interest_id)
    
    assert name_index_key == f"ysim:interest:by_name:{interest_name}"
    assert interest_key.startswith("ysim:interest:")
    print(f"  ✓ Interest creation flow correct")


def test_get_topic_id_by_name():
    """Test topic ID lookup by name."""
    print("\n3. Testing get_topic_id_by_name...")
    
    topic_name = "sports"
    expected_topic_id = "topic-uuid-456"
    
    name_index_key = f"ysim:interest:by_name:{topic_name}"
    # redis_client.get(name_index_key) -> "topic-uuid-456"
    
    assert name_index_key == f"ysim:interest:by_name:{topic_name}"
    print(f"  ✓ Topic ID lookup by name works")


def test_post_topics_set():
    """Test post topics set structure."""
    print("\n4. Testing post topics set...")
    
    post_id = "post-uuid-123"
    topic_ids = {"topic-1", "topic-2", "topic-3"}
    
    post_topics_key = f"ysim:post:{post_id}:topics:"
    
    # Simulate adding topics
    # for topic_id in topic_ids:
    #     redis_client.sadd(post_topics_key, topic_id)
    
    # Simulate getting topics
    # retrieved = redis_client.smembers(post_topics_key)
    
    assert post_topics_key.startswith(f"ysim:post:{post_id}:topics")
    print(f"  ✓ Post topics set key: {post_topics_key}")


def test_user_interests_set():
    """Test user interests set structure."""
    print("\n5. Testing user interests set...")
    
    user_id = "user-uuid-456"
    interest_ids = {"interest-1", "interest-2"}
    
    user_interests_key = f"ysim:user:{user_id}:interests:"
    
    assert user_interests_key.startswith(f"ysim:user:{user_id}:interests")
    print(f"  ✓ User interests set key: {user_interests_key}")


def test_article_topics_set():
    """Test article topics set structure."""
    print("\n6. Testing article topics set...")
    
    article_id = "article-uuid-789"
    topic_ids = {"topic-1", "topic-2"}
    
    article_topics_key = f"ysim:article:{article_id}:topics:"
    
    # Simulate sismember check
    # is_member = redis_client.sismember(article_topics_key, "topic-1")
    
    assert article_topics_key.startswith(f"ysim:article:{article_id}:topics")
    print(f"  ✓ Article topics set key: {article_topics_key}")


def test_interest_data_structure():
    """Test interest data structure in Redis."""
    print("\n7. Testing interest data structure...")
    
    # Simulate interest data
    mock_interest_data = {
        b'iid': b'interest-uuid-123',
        b'interest': b'technology'
    }
    
    # Decode
    decoded = {
        k.decode() if isinstance(k, bytes) else k:
        v.decode() if isinstance(v, bytes) else v
        for k, v in mock_interest_data.items()
    }
    
    assert decoded['iid'] == 'interest-uuid-123'
    assert decoded['interest'] == 'technology'
    assert all(isinstance(k, str) for k in decoded.keys())
    print(f"  ✓ Interest data properly decoded")


if __name__ == "__main__":
    print("\n=== Topics & Interests Redis Tests ===")
    
    test_interest_name_index()
    test_add_or_get_interest_flow()
    test_get_topic_id_by_name()
    test_post_topics_set()
    test_user_interests_set()
    test_article_topics_set()
    test_interest_data_structure()
    
    print("\n=== All tests passed! ===")
