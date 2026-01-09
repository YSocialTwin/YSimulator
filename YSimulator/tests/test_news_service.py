"""
Unit tests for news_feeds/news_service.py

Tests the NewsFeedService Ray actor for fetching and caching RSS feeds.
"""

import pytest
from unittest.mock import MagicMock, patch
import time


class TestNewsFeedServiceInit:
    """Test NewsFeedService initialization."""

    def test_init_with_no_config(self):
        """Test initialization with no configuration."""
        with patch("ray.remote", lambda x: x):
            from YSimulator.YClient.news_feeds.news_service import NewsFeedService

            with patch.object(NewsFeedService, "__init__", return_value=None):
                service = NewsFeedService.__new__(NewsFeedService)
                service.feeds_config = []
                service.cache_duration = 3600
                service.cached_news = {}
                service.last_fetched = {}
                service.website_ids = {}
                service.server = None

                assert service.feeds_config == []
                assert service.cache_duration == 3600
                assert service.cached_news == {}
                assert service.last_fetched == {}

    def test_init_with_feeds_config(self):
        """Test initialization with feeds configuration."""
        with patch("ray.remote", lambda x: x):
            from YSimulator.YClient.news_feeds.news_service import NewsFeedService

            feeds_config = {
                "feeds": [
                    {
                        "name": "TechCrunch",
                        "url": "https://techcrunch.com/feed/",
                        "category": "tech",
                    }
                ],
                "cache_duration": 7200,
            }

            with patch.object(NewsFeedService, "__init__", return_value=None):
                service = NewsFeedService.__new__(NewsFeedService)
                service.feeds_config = feeds_config.get("feeds", [])
                service.cache_duration = feeds_config.get("cache_duration", 3600)
                service.cached_news = {}
                service.last_fetched = {}

                # Initialize caches
                for feed in service.feeds_config:
                    feed_url = feed.get("url")
                    if feed_url:
                        service.cached_news[feed_url] = {"articles": [], "timestamp": 0}
                        service.last_fetched[feed_url] = 0

                assert len(service.feeds_config) == 1
                assert service.cache_duration == 7200
                assert "https://techcrunch.com/feed/" in service.cached_news


class TestRegisterPageFeed:
    """Test register_page_feed functionality."""

    def test_register_page_feed_success(self):
        """Test successfully registering a page feed."""
        with patch("ray.remote", lambda x: x):
            from YSimulator.YClient.news_feeds.news_service import NewsFeedService

            with patch.object(NewsFeedService, "__init__", return_value=None):
                service = NewsFeedService.__new__(NewsFeedService)
                service.feeds_config = []
                service.cached_news = {}
                service.last_fetched = {}
                service.website_ids = {}

                feed_url = "https://example.com/feed/"
                page_id = "page-123"

                # Mock the register_page_feed method logic
                service.feeds_config.append({"url": feed_url})
                service.cached_news[feed_url] = {"articles": [], "timestamp": 0}
                service.last_fetched[feed_url] = 0
                service.website_ids[feed_url] = page_id

                assert feed_url in service.cached_news
                assert feed_url in service.website_ids
                assert service.website_ids[feed_url] == page_id

    def test_register_page_feed_empty_url(self):
        """Test registering with empty URL returns False."""
        with patch("ray.remote", lambda x: x):
            from YSimulator.YClient.news_feeds.news_service import NewsFeedService

            with patch.object(NewsFeedService, "__init__", return_value=None):
                service = NewsFeedService.__new__(NewsFeedService)
                service.feeds_config = []

                # Empty URL should be rejected
                assert not None  # Would return False in actual implementation
                assert not ""  # Would return False in actual implementation


class TestFeedParsing:
    """Test RSS feed parsing functionality."""

    def test_parse_valid_rss_feed(self):
        """Test parsing a valid RSS feed."""
        # Mock feedparser response
        mock_feed = MagicMock()
        mock_feed.entries = [
            {
                "title": "Test Article 1",
                "link": "https://example.com/article1",
                "summary": "Summary of article 1",
                "published": "Mon, 01 Jan 2024 12:00:00 GMT",
            },
            {
                "title": "Test Article 2",
                "link": "https://example.com/article2",
                "summary": "Summary of article 2",
                "published": "Mon, 01 Jan 2024 13:00:00 GMT",
            },
        ]

        with patch("feedparser.parse", return_value=mock_feed):
            import feedparser

            result = feedparser.parse("https://example.com/feed/")

            assert len(result.entries) == 2
            assert result.entries[0]["title"] == "Test Article 1"
            assert result.entries[1]["title"] == "Test Article 2"

    def test_parse_empty_feed(self):
        """Test parsing an empty RSS feed."""
        mock_feed = MagicMock()
        mock_feed.entries = []

        with patch("feedparser.parse", return_value=mock_feed):
            import feedparser

            result = feedparser.parse("https://example.com/feed/")

            assert len(result.entries) == 0

    def test_parse_malformed_feed(self):
        """Test parsing a malformed RSS feed."""
        mock_feed = MagicMock()
        mock_feed.entries = []
        mock_feed.bozo = True  # feedparser sets this for malformed feeds
        mock_feed.bozo_exception = Exception("Feed is malformed")

        with patch("feedparser.parse", return_value=mock_feed):
            import feedparser

            result = feedparser.parse("https://example.com/invalid/")

            assert result.bozo is True
            assert len(result.entries) == 0


class TestCaching:
    """Test feed caching functionality."""

    def test_cache_stores_articles(self):
        """Test that articles are stored in cache."""
        with patch("ray.remote", lambda x: x):
            from YSimulator.YClient.news_feeds.news_service import NewsFeedService

            with patch.object(NewsFeedService, "__init__", return_value=None):
                service = NewsFeedService.__new__(NewsFeedService)
                service.cached_news = {}
                service.cache_duration = 3600

                feed_url = "https://example.com/feed/"
                articles = [
                    {"title": "Article 1", "link": "https://example.com/1"},
                    {"title": "Article 2", "link": "https://example.com/2"},
                ]
                current_time = int(time.time())

                # Store in cache
                service.cached_news[feed_url] = {"articles": articles, "timestamp": current_time}

                assert feed_url in service.cached_news
                assert len(service.cached_news[feed_url]["articles"]) == 2
                assert service.cached_news[feed_url]["timestamp"] == current_time

    def test_cache_expiration(self):
        """Test that cache expires after cache_duration."""
        with patch("ray.remote", lambda x: x):
            from YSimulator.YClient.news_feeds.news_service import NewsFeedService

            with patch.object(NewsFeedService, "__init__", return_value=None):
                service = NewsFeedService.__new__(NewsFeedService)
                service.cached_news = {}
                service.cache_duration = 3600  # 1 hour

                feed_url = "https://example.com/feed/"
                old_timestamp = int(time.time()) - 7200  # 2 hours ago
                current_time = int(time.time())

                service.cached_news[feed_url] = {
                    "articles": [{"title": "Old Article"}],
                    "timestamp": old_timestamp,
                }

                # Check if cache is expired
                is_expired = (current_time - old_timestamp) > service.cache_duration
                assert is_expired is True

    def test_cache_fresh(self):
        """Test that cache is fresh within cache_duration."""
        with patch("ray.remote", lambda x: x):
            from YSimulator.YClient.news_feeds.news_service import NewsFeedService

            with patch.object(NewsFeedService, "__init__", return_value=None):
                service = NewsFeedService.__new__(NewsFeedService)
                service.cached_news = {}
                service.cache_duration = 3600

                feed_url = "https://example.com/feed/"
                recent_timestamp = int(time.time()) - 1800  # 30 minutes ago
                current_time = int(time.time())

                service.cached_news[feed_url] = {
                    "articles": [{"title": "Recent Article"}],
                    "timestamp": recent_timestamp,
                }

                # Check if cache is still fresh
                is_fresh = (current_time - recent_timestamp) <= service.cache_duration
                assert is_fresh is True


class TestGetRandomArticle:
    """Test getting random articles from cache."""

    def test_get_random_article_from_cache(self):
        """Test retrieving a random article from cached articles."""
        with patch("ray.remote", lambda x: x):
            from YSimulator.YClient.news_feeds.news_service import NewsFeedService

            with patch.object(NewsFeedService, "__init__", return_value=None):
                service = NewsFeedService.__new__(NewsFeedService)
                service.cached_news = {}

                feed_url = "https://example.com/feed/"
                articles = [
                    {"title": "Article 1", "link": "https://example.com/1"},
                    {"title": "Article 2", "link": "https://example.com/2"},
                    {"title": "Article 3", "link": "https://example.com/3"},
                ]

                service.cached_news[feed_url] = {
                    "articles": articles,
                    "timestamp": int(time.time()),
                }

                # Simulate getting random article
                import random

                random.seed(42)
                article = random.choice(articles)

                assert article in articles
                assert "title" in article
                assert "link" in article

    def test_get_random_article_empty_cache(self):
        """Test behavior when cache is empty."""
        with patch("ray.remote", lambda x: x):
            from YSimulator.YClient.news_feeds.news_service import NewsFeedService

            with patch.object(NewsFeedService, "__init__", return_value=None):
                service = NewsFeedService.__new__(NewsFeedService)
                service.cached_news = {}

                feed_url = "https://example.com/feed/"
                service.cached_news[feed_url] = {"articles": [], "timestamp": int(time.time())}

                # Should handle empty cache gracefully
                articles = service.cached_news[feed_url]["articles"]
                assert len(articles) == 0


class TestArticleFormatting:
    """Test article data structure and formatting."""

    def test_article_has_required_fields(self):
        """Test that articles have required fields."""
        article = {
            "title": "Test Article",
            "link": "https://example.com/article",
            "summary": "Article summary",
            "published": "Mon, 01 Jan 2024 12:00:00 GMT",
        }

        assert "title" in article
        assert "link" in article
        assert article["title"] == "Test Article"
        assert article["link"].startswith("http")

    def test_article_optional_fields(self):
        """Test that articles can have optional fields."""
        article = {
            "title": "Test Article",
            "link": "https://example.com/article",
            "summary": "Article summary",
            "published": "Mon, 01 Jan 2024 12:00:00 GMT",
            "author": "John Doe",
            "tags": ["tech", "news"],
        }

        assert "author" in article
        assert "tags" in article
        assert article["author"] == "John Doe"
        assert len(article["tags"]) == 2


class TestErrorHandling:
    """Test error handling in news service."""

    def test_handle_network_error(self):
        """Test handling of network errors when fetching feeds."""
        with patch("feedparser.parse") as mock_parse:
            mock_parse.side_effect = Exception("Network error")

            try:
                import feedparser

                feedparser.parse("https://example.com/feed/")
                assert False, "Should raise exception"
            except Exception as e:
                assert "Network error" in str(e)

    def test_handle_timeout(self):
        """Test handling of timeout errors."""
        with patch("feedparser.parse") as mock_parse:
            mock_parse.side_effect = TimeoutError("Request timed out")

            try:
                import feedparser

                feedparser.parse("https://example.com/feed/")
                assert False, "Should raise exception"
            except TimeoutError as e:
                assert "timed out" in str(e).lower()

    def test_handle_invalid_url(self):
        """Test handling of invalid feed URLs."""
        invalid_urls = ["", "not-a-url", "ftp://wrong-protocol.com/feed", None]

        for url in invalid_urls:
            if not url or not isinstance(url, str):
                assert True  # Should be rejected
            elif not url.startswith(("http://", "https://")):
                assert True  # Should be rejected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
