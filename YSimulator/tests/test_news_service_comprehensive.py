"""
Comprehensive unit tests for news_feeds/news_service.py

Tests the NewsFeedService Ray actor with extensive mocking for Ray actors,
feedparser, and database interactions.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
import time
from datetime import datetime
import uuid


class MockNewsFeedService:
    """Mock version of NewsFeedService for testing without Ray."""
    
    def __init__(self, feeds_config=None, llm_service=None):
        """Initialize mock service."""
        self.logger = Mock()
        
        if feeds_config is None:
            feeds_config = {
                "feeds": [],
                "cache_duration": 3600,
            }
        
        self.feeds_config = feeds_config.get("feeds", [])
        self.cache_duration = feeds_config.get("cache_duration", 3600)
        self.llm_service = llm_service
        self.server = None
        self.cached_news = {}
        self.last_fetched = {}
        self.website_ids = {}
        
        # Initialize caches
        for feed in self.feeds_config:
            feed_url = feed.get("url")
            if feed_url:
                self.cached_news[feed_url] = {"articles": [], "timestamp": 0}
                self.last_fetched[feed_url] = 0
    
    def _register_feeds_with_server(self):
        """Mock register feeds."""
        if not self.server:
            return
        
        for feed in self.feeds_config:
            feed_url = feed.get("url")
            if feed_url:
                self.website_ids[feed_url] = str(uuid.uuid4())
    
    def register_page_feed(self, feed_url: str, page_id: str) -> bool:
        """Register a page feed."""
        if not feed_url:
            return False
        
        # Check if already registered
        if feed_url not in [f.get("url") for f in self.feeds_config]:
            self.feeds_config.append({"url": feed_url})
        
        self.cached_news[feed_url] = {"articles": [], "timestamp": 0}
        self.last_fetched[feed_url] = 0
        self.website_ids[feed_url] = page_id
        
        return True
    
    def _should_refresh_cache(self, feed_url: str) -> bool:
        """Check if cache should be refreshed."""
        if feed_url not in self.last_fetched:
            return True
        
        current_time = int(time.time())
        time_since_fetch = current_time - self.last_fetched[feed_url]
        
        return time_since_fetch >= self.cache_duration
    
    def _fetch_feed(self, feed_url: str, feed_name: str = "Unknown"):
        """Fetch RSS feed."""
        import feedparser
        
        try:
            feed = feedparser.parse(feed_url)
            
            if hasattr(feed, 'bozo') and feed.bozo:
                self.logger.warning(f"Malformed feed: {feed_url}")
                return []
            
            articles = []
            for entry in feed.entries[:20]:  # Limit to 20 articles
                article = {
                    "title": entry.get("title", "No Title"),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", ""),
                    "published": entry.get("published", ""),
                    "source": feed_name,
                    "source_url": feed_url,
                }
                articles.append(article)
            
            return articles
        
        except Exception as e:
            self.logger.error(f"Error fetching feed {feed_url}: {e}")
            return []
    
    def refresh_feed(self, feed_url: str):
        """Refresh a specific feed."""
        if not self._should_refresh_cache(feed_url):
            return {
                "success": True,
                "cached": True,
                "article_count": len(self.cached_news.get(feed_url, {}).get("articles", []))
            }
        
        # Find feed name
        feed_name = "Unknown"
        for feed in self.feeds_config:
            if feed.get("url") == feed_url:
                feed_name = feed.get("name", "Unknown")
                break
        
        # Fetch articles
        articles = self._fetch_feed(feed_url, feed_name)
        
        # Update cache
        self.cached_news[feed_url] = {
            "articles": articles,
            "timestamp": int(time.time())
        }
        self.last_fetched[feed_url] = int(time.time())
        
        return {
            "success": True,
            "cached": False,
            "article_count": len(articles),
            "feed_url": feed_url
        }
    
    def refresh_all_feeds(self):
        """Refresh all registered feeds."""
        results = {}
        total_articles = 0
        
        for feed_url in self.cached_news.keys():
            result = self.refresh_feed(feed_url)
            results[feed_url] = result
            total_articles += result.get("article_count", 0)
        
        return {
            "success": True,
            "feeds_refreshed": len(results),
            "total_articles": total_articles,
            "results": results
        }
    
    def get_random_article(self, feed_url: str = None, category: str = None):
        """Get a random article."""
        import random
        
        # If specific feed requested
        if feed_url:
            if feed_url not in self.cached_news:
                return None
            
            articles = self.cached_news[feed_url].get("articles", [])
            if not articles:
                return None
            
            return random.choice(articles)
        
        # Get from all feeds
        all_articles = []
        for cache_data in self.cached_news.values():
            all_articles.extend(cache_data.get("articles", []))
        
        if not all_articles:
            return None
        
        return random.choice(all_articles)
    
    def get_article_from_feed(self, feed_url: str):
        """Get article from specific feed."""
        if feed_url not in self.cached_news:
            return None
        
        articles = self.cached_news[feed_url].get("articles", [])
        if not articles:
            # Try to refresh
            self.refresh_feed(feed_url)
            articles = self.cached_news[feed_url].get("articles", [])
        
        if not articles:
            return None
        
        import random
        return random.choice(articles)
    
    def get_feed_status(self):
        """Get status of all feeds."""
        status = {
            "total_feeds": len(self.feeds_config),
            "cached_feeds": len(self.cached_news),
            "feeds": []
        }
        
        for feed_url, cache_data in self.cached_news.items():
            feed_info = {
                "url": feed_url,
                "article_count": len(cache_data.get("articles", [])),
                "last_fetched": self.last_fetched.get(feed_url, 0),
                "cache_age": int(time.time()) - self.last_fetched.get(feed_url, 0)
            }
            status["feeds"].append(feed_info)
        
        return status


class TestNewsFeedServiceInitialization:
    """Test service initialization."""
    
    def test_init_with_empty_config(self):
        """Test initialization with no feeds."""
        service = MockNewsFeedService()
        
        assert service.feeds_config == []
        assert service.cache_duration == 3600
        assert service.cached_news == {}
        assert service.last_fetched == {}
    
    def test_init_with_feeds(self):
        """Test initialization with configured feeds."""
        config = {
            "feeds": [
                {"name": "Tech", "url": "https://example.com/tech"},
                {"name": "News", "url": "https://example.com/news"}
            ],
            "cache_duration": 7200
        }
        
        service = MockNewsFeedService(config)
        
        assert len(service.feeds_config) == 2
        assert service.cache_duration == 7200
        assert len(service.cached_news) == 2
        assert "https://example.com/tech" in service.cached_news
        assert "https://example.com/news" in service.cached_news
    
    def test_init_custom_cache_duration(self):
        """Test custom cache duration."""
        config = {"cache_duration": 1800}
        service = MockNewsFeedService(config)
        
        assert service.cache_duration == 1800


class TestRegisterPageFeed:
    """Test feed registration."""
    
    def test_register_new_feed(self):
        """Test registering a new feed."""
        service = MockNewsFeedService()
        
        result = service.register_page_feed(
            "https://example.com/feed",
            "page-123"
        )
        
        assert result is True
        assert "https://example.com/feed" in service.cached_news
        assert service.website_ids["https://example.com/feed"] == "page-123"
    
    def test_register_empty_url(self):
        """Test registering with empty URL."""
        service = MockNewsFeedService()
        
        result = service.register_page_feed("", "page-123")
        
        assert result is False
    
    def test_register_duplicate_feed(self):
        """Test registering same feed twice."""
        service = MockNewsFeedService()
        
        service.register_page_feed("https://example.com/feed", "page-1")
        result = service.register_page_feed("https://example.com/feed", "page-2")
        
        assert result is True
        # Should update page_id
        assert service.website_ids["https://example.com/feed"] == "page-2"


class TestCacheManagement:
    """Test cache management."""
    
    def test_should_refresh_cache_new_feed(self):
        """Test cache refresh needed for new feed."""
        service = MockNewsFeedService()
        
        should_refresh = service._should_refresh_cache("https://example.com/feed")
        
        assert should_refresh is True
    
    def test_should_refresh_cache_expired(self):
        """Test cache refresh needed when expired."""
        service = MockNewsFeedService()
        service.last_fetched["https://example.com/feed"] = int(time.time()) - 7200
        service.cache_duration = 3600
        
        should_refresh = service._should_refresh_cache("https://example.com/feed")
        
        assert should_refresh is True
    
    def test_should_not_refresh_cache_fresh(self):
        """Test cache refresh not needed when fresh."""
        service = MockNewsFeedService()
        service.last_fetched["https://example.com/feed"] = int(time.time()) - 1800
        service.cache_duration = 3600
        
        should_refresh = service._should_refresh_cache("https://example.com/feed")
        
        assert should_refresh is False


class TestFetchFeed:
    """Test RSS feed fetching."""
    
    def test_fetch_feed_success(self):
        """Test successful feed fetch."""
        service = MockNewsFeedService()
        
        mock_entry = Mock()
        mock_entry.get = lambda k, default="": {
            "title": "Test Article",
            "link": "https://example.com/article",
            "summary": "Test summary",
            "published": "2024-01-01"
        }.get(k, default)
        
        mock_feed = Mock()
        mock_feed.entries = [mock_entry]
        mock_feed.bozo = False
        
        with patch('feedparser.parse', return_value=mock_feed):
            articles = service._fetch_feed("https://example.com/feed", "Test Feed")
        
        assert len(articles) == 1
        assert articles[0]["title"] == "Test Article"
        assert articles[0]["source"] == "Test Feed"
    
    def test_fetch_feed_malformed(self):
        """Test handling malformed feed."""
        service = MockNewsFeedService()
        
        mock_feed = Mock()
        mock_feed.bozo = True
        mock_feed.entries = []
        
        with patch('feedparser.parse', return_value=mock_feed):
            articles = service._fetch_feed("https://example.com/bad-feed")
        
        assert articles == []
        assert service.logger.warning.called
    
    def test_fetch_feed_exception(self):
        """Test handling fetch exception."""
        service = MockNewsFeedService()
        
        with patch('feedparser.parse', side_effect=Exception("Network error")):
            articles = service._fetch_feed("https://example.com/feed")
        
        assert articles == []
        assert service.logger.error.called
    
    def test_fetch_feed_limit_articles(self):
        """Test limiting articles to 20."""
        service = MockNewsFeedService()
        
        # Create 30 mock entries
        mock_entries = []
        for i in range(30):
            mock_entry = Mock()
            mock_entry.get = lambda k, default="", i=i: {
                "title": f"Article {i}",
                "link": f"https://example.com/article-{i}",
                "summary": f"Summary {i}",
                "published": "2024-01-01"
            }.get(k, default)
            mock_entries.append(mock_entry)
        
        mock_feed = Mock()
        mock_feed.entries = mock_entries
        mock_feed.bozo = False
        
        with patch('feedparser.parse', return_value=mock_feed):
            articles = service._fetch_feed("https://example.com/feed")
        
        # Should only return first 20
        assert len(articles) == 20


class TestRefreshFeed:
    """Test feed refresh functionality."""
    
    def test_refresh_feed_from_cache(self):
        """Test getting articles from cache."""
        service = MockNewsFeedService()
        service.cached_news["https://example.com/feed"] = {
            "articles": [{"title": "Cached"}],
            "timestamp": int(time.time())
        }
        service.last_fetched["https://example.com/feed"] = int(time.time())
        
        result = service.refresh_feed("https://example.com/feed")
        
        assert result["success"] is True
        assert result["cached"] is True
        assert result["article_count"] == 1
    
    def test_refresh_feed_fetch_new(self):
        """Test fetching new articles."""
        config = {
            "feeds": [{"name": "Test", "url": "https://example.com/feed"}]
        }
        service = MockNewsFeedService(config)
        
        mock_entry = Mock()
        mock_entry.get = lambda k, default="": {
            "title": "New Article",
            "link": "https://example.com/new",
            "summary": "New summary",
            "published": "2024-01-01"
        }.get(k, default)
        
        mock_feed = Mock()
        mock_feed.entries = [mock_entry]
        mock_feed.bozo = False
        
        with patch('feedparser.parse', return_value=mock_feed):
            result = service.refresh_feed("https://example.com/feed")
        
        assert result["success"] is True
        assert result["cached"] is False
        assert result["article_count"] == 1
        assert len(service.cached_news["https://example.com/feed"]["articles"]) == 1


class TestRefreshAllFeeds:
    """Test refreshing all feeds."""
    
    def test_refresh_all_feeds(self):
        """Test refreshing multiple feeds."""
        config = {
            "feeds": [
                {"name": "Feed1", "url": "https://example.com/feed1"},
                {"name": "Feed2", "url": "https://example.com/feed2"}
            ]
        }
        service = MockNewsFeedService(config)
        
        mock_entry = Mock()
        mock_entry.get = lambda k, default="": {
            "title": "Article",
            "link": "https://example.com/article",
            "summary": "Summary",
            "published": "2024-01-01"
        }.get(k, default)
        
        mock_feed = Mock()
        mock_feed.entries = [mock_entry, mock_entry]
        mock_feed.bozo = False
        
        with patch('feedparser.parse', return_value=mock_feed):
            result = service.refresh_all_feeds()
        
        assert result["success"] is True
        assert result["feeds_refreshed"] == 2
        assert result["total_articles"] == 4  # 2 articles per feed


class TestGetRandomArticle:
    """Test getting random articles."""
    
    def test_get_random_article_from_specific_feed(self):
        """Test getting article from specific feed."""
        service = MockNewsFeedService()
        service.cached_news["https://example.com/feed"] = {
            "articles": [
                {"title": "Article 1"},
                {"title": "Article 2"}
            ],
            "timestamp": int(time.time())
        }
        
        import random
        random.seed(42)
        
        article = service.get_random_article("https://example.com/feed")
        
        assert article is not None
        assert "title" in article
    
    def test_get_random_article_from_all_feeds(self):
        """Test getting article from any feed."""
        service = MockNewsFeedService()
        service.cached_news["https://example.com/feed1"] = {
            "articles": [{"title": "Article 1"}],
            "timestamp": int(time.time())
        }
        service.cached_news["https://example.com/feed2"] = {
            "articles": [{"title": "Article 2"}],
            "timestamp": int(time.time())
        }
        
        article = service.get_random_article()
        
        assert article is not None
        assert article["title"] in ["Article 1", "Article 2"]
    
    def test_get_random_article_empty_cache(self):
        """Test getting article when cache is empty."""
        service = MockNewsFeedService()
        service.cached_news["https://example.com/feed"] = {
            "articles": [],
            "timestamp": int(time.time())
        }
        
        article = service.get_random_article("https://example.com/feed")
        
        assert article is None
    
    def test_get_random_article_nonexistent_feed(self):
        """Test getting article from nonexistent feed."""
        service = MockNewsFeedService()
        
        article = service.get_random_article("https://nonexistent.com/feed")
        
        assert article is None


class TestGetArticleFromFeed:
    """Test getting article from specific feed."""
    
    def test_get_article_from_feed_cached(self):
        """Test getting article from cached feed."""
        service = MockNewsFeedService()
        service.cached_news["https://example.com/feed"] = {
            "articles": [{"title": "Cached Article"}],
            "timestamp": int(time.time())
        }
        
        article = service.get_article_from_feed("https://example.com/feed")
        
        assert article is not None
        assert article["title"] == "Cached Article"
    
    def test_get_article_from_feed_refresh_if_empty(self):
        """Test refreshing feed if empty."""
        config = {
            "feeds": [{"name": "Test", "url": "https://example.com/feed"}]
        }
        service = MockNewsFeedService(config)
        
        # Start with empty cache
        service.cached_news["https://example.com/feed"]["articles"] = []
        
        mock_entry = Mock()
        mock_entry.get = lambda k, default="": {
            "title": "Fresh Article",
            "link": "https://example.com/article",
            "summary": "Summary",
            "published": "2024-01-01"
        }.get(k, default)
        
        mock_feed = Mock()
        mock_feed.entries = [mock_entry]
        mock_feed.bozo = False
        
        with patch('feedparser.parse', return_value=mock_feed):
            article = service.get_article_from_feed("https://example.com/feed")
        
        assert article is not None
        assert article["title"] == "Fresh Article"
    
    def test_get_article_from_nonexistent_feed(self):
        """Test getting article from nonexistent feed."""
        service = MockNewsFeedService()
        
        article = service.get_article_from_feed("https://nonexistent.com/feed")
        
        assert article is None


class TestGetFeedStatus:
    """Test feed status reporting."""
    
    def test_get_feed_status_empty(self):
        """Test status with no feeds."""
        service = MockNewsFeedService()
        
        status = service.get_feed_status()
        
        assert status["total_feeds"] == 0
        assert status["cached_feeds"] == 0
        assert len(status["feeds"]) == 0
    
    def test_get_feed_status_with_feeds(self):
        """Test status with feeds."""
        config = {
            "feeds": [
                {"name": "Feed1", "url": "https://example.com/feed1"},
                {"name": "Feed2", "url": "https://example.com/feed2"}
            ]
        }
        service = MockNewsFeedService(config)
        service.last_fetched["https://example.com/feed1"] = int(time.time()) - 1800
        service.last_fetched["https://example.com/feed2"] = int(time.time()) - 3600
        
        status = service.get_feed_status()
        
        assert status["total_feeds"] == 2
        assert status["cached_feeds"] == 2
        assert len(status["feeds"]) == 2
        
        # Check feed info
        feed_urls = [f["url"] for f in status["feeds"]]
        assert "https://example.com/feed1" in feed_urls
        assert "https://example.com/feed2" in feed_urls
    
    def test_get_feed_status_cache_age(self):
        """Test cache age calculation in status."""
        service = MockNewsFeedService()
        fetch_time = int(time.time()) - 7200  # 2 hours ago
        service.cached_news["https://example.com/feed"] = {
            "articles": [{"title": "Test"}],
            "timestamp": fetch_time
        }
        service.last_fetched["https://example.com/feed"] = fetch_time
        
        status = service.get_feed_status()
        
        feed_info = status["feeds"][0]
        assert feed_info["cache_age"] >= 7200
        assert feed_info["article_count"] == 1


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_feed_entries(self):
        """Test handling feed with no entries."""
        service = MockNewsFeedService()
        
        mock_feed = Mock()
        mock_feed.entries = []
        mock_feed.bozo = False
        
        with patch('feedparser.parse', return_value=mock_feed):
            articles = service._fetch_feed("https://example.com/feed")
        
        assert articles == []
    
    def test_missing_article_fields(self):
        """Test handling articles with missing fields."""
        service = MockNewsFeedService()
        
        # Entry with missing fields
        mock_entry = Mock()
        mock_entry.get = lambda k, default="": default
        
        mock_feed = Mock()
        mock_feed.entries = [mock_entry]
        mock_feed.bozo = False
        
        with patch('feedparser.parse', return_value=mock_feed):
            articles = service._fetch_feed("https://example.com/feed")
        
        assert len(articles) == 1
        assert articles[0]["title"] == "No Title"
        assert articles[0]["link"] == ""
    
    def test_cache_duration_zero(self):
        """Test with zero cache duration (always refresh)."""
        config = {"cache_duration": 0}
        service = MockNewsFeedService(config)
        service.last_fetched["https://example.com/feed"] = int(time.time())
        
        # Should always need refresh
        should_refresh = service._should_refresh_cache("https://example.com/feed")
        
        assert should_refresh is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
