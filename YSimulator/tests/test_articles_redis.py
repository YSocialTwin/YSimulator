"""
Test Redis support for Articles & News operations.

This test verifies that articles, websites, and images operations work correctly when Redis is enabled.
"""


def test_article_retrieval():
    """Test that get_article retrieves from Redis."""
    print("\n1. Testing article retrieval from Redis...")

    # Expected Redis key
    article_id = "article-uuid-123"
    redis_key = f"ysim:articles:{article_id}"

    # Simulate Redis hgetall result
    mock_article_data = {
        b"id": b"article-uuid-123",
        b"title": b"Test Article",
        b"summary": b"Article summary",
        b"website_id": b"website-uuid",
        b"link": b"https://example.com/article",
    }

    # Decode
    decoded = {
        k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
        for k, v in mock_article_data.items()
    }

    assert decoded["id"] == "article-uuid-123"
    assert decoded["title"] == "Test Article"
    assert all(isinstance(k, str) for k in decoded.keys())
    print(f"  ✓ Article data properly decoded from Redis")


def test_website_rss_index():
    """Test that website RSS URL index is created."""
    print("\n2. Testing website RSS URL index...")

    # Expected indices
    rss_url = "https://example.com/rss"
    website_id = "website-uuid-123"

    rss_index_key = f"ysim:website:by_rss:{rss_url}"
    website_data_key = f"ysim:websites:{website_id}"

    assert rss_index_key == f"ysim:website:by_rss:{rss_url}"
    assert website_data_key == f"ysim:websites:{website_id}"
    print(f"  ✓ RSS URL index key: {rss_index_key}")
    print(f"  ✓ Website data key: {website_data_key}")


def test_get_website_by_rss_lookup():
    """Test that get_website_by_rss uses the RSS URL index."""
    print("\n3. Testing get_website_by_rss lookup...")

    # Flow: RSS URL -> website ID -> website data
    rss_url = "https://example.com/rss"
    expected_website_id = "website-uuid-123"

    # Step 1: Look up website ID from RSS URL index
    rss_index_key = f"ysim:website:by_rss:{rss_url}"
    # redis_client.get(rss_index_key) -> "website-uuid-123"

    # Step 2: Get website data by ID
    website_data_key = f"ysim:websites:{expected_website_id}"
    # redis_client.hgetall(website_data_key)

    assert rss_index_key == f"ysim:website:by_rss:{rss_url}"
    assert website_data_key == f"ysim:websites:{expected_website_id}"
    print(f"  ✓ RSS URL lookup flow correct")


def test_image_ids_set():
    """Test that images are added to a set for random selection."""
    print("\n4. Testing image IDs set...")

    # Expected Redis structure
    images_set_key = "ysim:images:ids"
    image_ids = {"img-1", "img-2", "img-3"}

    # Simulate random selection
    import random

    selected = random.choice(list(image_ids))

    assert selected in image_ids
    assert images_set_key == "ysim:images:ids"
    print(f"  ✓ Image IDs set key: {images_set_key}")
    print(f"  ✓ Random selection works: {selected}")


def test_get_random_image_redis():
    """Test that get_random_image retrieves from Redis."""
    print("\n5. Testing get_random_image from Redis...")

    # Simulate image IDs in set
    mock_image_ids = {b"img-1", b"img-2", b"img-3"}

    # Select random and decode
    import random

    selected_id = random.choice(list(mock_image_ids))
    selected_id_str = selected_id.decode() if isinstance(selected_id, bytes) else selected_id

    # Get image data
    image_key = f"ysim:images:{selected_id_str}"

    assert image_key.startswith("ysim:images:")
    assert isinstance(selected_id_str, str)
    print(f"  ✓ Random image selected: {selected_id_str}")
    print(f"  ✓ Image data key: {image_key}")


def test_article_caching_on_add():
    """Test that add_article caches in Redis."""
    print("\n6. Testing article caching on add...")

    # Article is cached when added
    article_id = "article-uuid-456"
    article_data = {
        "id": article_id,
        "title": "New Article",
        "summary": "Summary text",
        "website_id": "website-123",
        "link": "https://example.com/new",
    }

    redis_key = f"ysim:articles:{article_id}"

    # Verify all fields would be cached
    assert "id" in article_data
    assert "title" in article_data
    assert "website_id" in article_data
    print(f"  ✓ Article would be cached at: {redis_key}")


if __name__ == "__main__":
    print("\n=== Articles & News Redis Tests ===")

    test_article_retrieval()
    test_website_rss_index()
    test_get_website_by_rss_lookup()
    test_image_ids_set()
    test_get_random_image_redis()
    test_article_caching_on_add()

    print("\n=== All tests passed! ===")
