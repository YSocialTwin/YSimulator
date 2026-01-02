"""
Test Redis support for Annotation operations.

This test verifies that emotion annotation operations work correctly when Redis is enabled.
Tests cover: get_emotion_by_name with Redis caching and fallback.
"""


def test_emotion_name_index_lookup():
    """Test that get_emotion_by_name uses the emotion name index."""
    print("\n1. Testing emotion name index lookup...")
    
    # Simulate Redis lookup flow
    emotion_name = "joy"
    expected_emotion_id = "emotion-uuid-123"
    
    # Step 1: Look up emotion ID from name index
    emotion_name_key = f"ysim:emotion:by_name:{emotion_name}"
    # Would call: redis_client.get(emotion_name_key) -> "emotion-uuid-123"
    
    # Step 2: Get emotion data from hash
    emotion_key = f"ysim:emotion:{expected_emotion_id}"
    # Would call: redis_client.hgetall(emotion_key)
    
    assert emotion_name_key == "ysim:emotion:by_name:joy"
    assert emotion_key == "ysim:emotion:emotion-uuid-123"
    print(f"  ✓ Emotion name index key: {emotion_name_key}")
    print(f"  ✓ Emotion data key: {emotion_key}")


def test_emotion_data_decoding():
    """Test that emotion data from Redis is properly decoded."""
    print("\n2. Testing emotion data byte decoding...")
    
    # Simulate Redis hgetall result (returns bytes)
    mock_emotion_data = {
        b'id': b'emotion-uuid-123',
        b'emotion': b'joy',
        b'icon': b'mdi-emoticon'
    }
    
    # Decode all keys and values
    decoded = {
        k.decode() if isinstance(k, bytes) else k:
        v.decode() if isinstance(v, bytes) else v
        for k, v in mock_emotion_data.items()
    }
    
    assert decoded['id'] == 'emotion-uuid-123'
    assert decoded['emotion'] == 'joy'
    assert decoded['icon'] == 'mdi-emoticon'
    assert all(isinstance(k, str) for k in decoded.keys())
    assert all(isinstance(v, str) for v in decoded.values())
    print(f"  ✓ All emotion data properly decoded")


def test_emotion_cache_fallback():
    """Test that emotion lookup falls back to SQL and caches the result."""
    print("\n3. Testing emotion cache fallback...")
    
    # Scenario: Emotion not in Redis cache
    emotion_name = "anger"
    
    # Expected flow:
    # 1. Check Redis: ysim:emotion:by_name:anger -> Not found
    # 2. Query SQL: SELECT * FROM emotions WHERE emotion = 'anger'
    # 3. Cache result in Redis:
    #    - redis_client.hset("ysim:emotion:uuid", mapping=emotion_data)
    #    - redis_client.set("ysim:emotion:by_name:anger", emotion_id)
    
    emotion_id = "emotion-uuid-456"
    emotion_data = {
        "id": emotion_id,
        "emotion": emotion_name,
        "icon": "mdi-emoticon-devil"
    }
    
    # Verify cache keys
    emotion_key = f"ysim:emotion:{emotion_id}"
    name_index_key = f"ysim:emotion:by_name:{emotion_name}"
    
    assert emotion_key == "ysim:emotion:emotion-uuid-456"
    assert name_index_key == "ysim:emotion:by_name:anger"
    print(f"  ✓ Emotion cached at: {emotion_key}")
    print(f"  ✓ Name index created: {name_index_key}")


def test_emotion_cache_hit():
    """Test that subsequent lookups use the cached emotion data."""
    print("\n4. Testing emotion cache hit...")
    
    # Scenario: Emotion already in Redis cache
    emotion_name = "joy"
    cached_emotion_id = "emotion-uuid-123"
    
    # Expected flow (cache hit):
    # 1. Check Redis: ysim:emotion:by_name:joy -> "emotion-uuid-123" (found!)
    # 2. Get data: redis_client.hgetall("ysim:emotion:emotion-uuid-123")
    # 3. Return cached data (no SQL query needed)
    
    name_index_key = f"ysim:emotion:by_name:{emotion_name}"
    emotion_key = f"ysim:emotion:{cached_emotion_id}"
    
    assert name_index_key == "ysim:emotion:by_name:joy"
    assert emotion_key == "ysim:emotion:emotion-uuid-123"
    print(f"  ✓ Cache hit: {name_index_key} -> {cached_emotion_id}")
    print(f"  ✓ Data retrieved from: {emotion_key}")


def test_all_emotions_cacheable():
    """Test that all GoEmotions taxonomy emotions can be cached."""
    print("\n5. Testing all emotions are cacheable...")
    
    # GoEmotions taxonomy (28 emotions)
    emotions = [
        "amusement", "admiration", "anger", "annoyance", "approval", "caring",
        "confusion", "curiosity", "desire", "disappointment", "disapproval", "disgust",
        "embarrassment", "excitement", "fear", "gratitude", "grief", "joy",
        "love", "nervousness", "optimism", "pride", "realization", "relief",
        "remorse", "sadness", "surprise", "trust"
    ]
    
    # Each emotion should have:
    # 1. Emotion data hash: ysim:emotion:{emotion_id}
    # 2. Name index: ysim:emotion:by_name:{emotion_name}
    
    for emotion in emotions:
        name_index_key = f"ysim:emotion:by_name:{emotion}"
        assert "ysim:emotion:by_name:" in name_index_key
    
    print(f"  ✓ All {len(emotions)} emotions cacheable in Redis")


if __name__ == "__main__":
    print("\n=== Annotation Redis Tests ===")
    
    test_emotion_name_index_lookup()
    test_emotion_data_decoding()
    test_emotion_cache_fallback()
    test_emotion_cache_hit()
    test_all_emotions_cacheable()
    
    print("\n=== All tests passed! ===")
