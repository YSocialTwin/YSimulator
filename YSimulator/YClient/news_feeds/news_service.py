"""
News Feed Service - Ray Actor for Async News Fetching

This module provides a Ray-based asynchronous news feed service for the Y social 
network simulation. It handles fetching articles from RSS feeds, caching them,
and providing news content for agent actions.

The service is designed to work asynchronously similar to LLMService to avoid
blocking simulation execution.
"""

import ray
import feedparser
import datetime
import random
from typing import Dict, List, Optional, Tuple
import time


@ray.remote
class NewsFeedService:
    """
    Ray actor for managing news feeds asynchronously.
    
    This service fetches news articles from configured RSS feeds, caches them
    to avoid redundant parsing, and provides random articles for agent news
    posting actions. It tracks when each feed was last accessed to implement
    intelligent caching.
    
    Attributes:
        feeds_config (dict): Configuration of news feeds
        cached_news (dict): Cache of fetched news articles by feed URL
        last_fetched (dict): Timestamp of last fetch per feed URL
        cache_duration (int): Cache duration in seconds (default: 3600)
    """
    
    def __init__(self, feeds_config: Optional[Dict] = None):
        """
        Initialize the NewsFeedService actor.
        
        Args:
            feeds_config (dict, optional): Configuration dictionary with feed URLs
                Example:
                {
                    "feeds": [
                        {
                            "name": "TechCrunch",
                            "url": "https://techcrunch.com/feed/",
                            "category": "tech",
                            "language": "en"
                        }
                    ],
                    "cache_duration": 3600  # seconds
                }
        """
        # Load configuration with defaults
        if feeds_config is None:
            feeds_config = {
                "feeds": [
                    {
                        "name": "BBC News",
                        "url": "http://feeds.bbci.co.uk/news/rss.xml",
                        "category": "general",
                        "language": "en"
                    }
                ],
                "cache_duration": 3600  # 1 hour
            }
        
        self.feeds_config = feeds_config.get("feeds", [])
        self.cache_duration = feeds_config.get("cache_duration", 3600)
        
        # Get server actor reference
        try:
            self.server = ray.get_actor("Orchestrator")
        except:
            self.server = None
        
        # Cache structure: {feed_url: {"articles": [...], "timestamp": int, "website_id": str}}
        self.cached_news = {}
        self.last_fetched = {}
        self.website_ids = {}  # Map feed_url to website_id
        
        # Initialize caches for all configured feeds
        for feed in self.feeds_config:
            feed_url = feed.get("url")
            if feed_url:
                self.cached_news[feed_url] = {"articles": [], "timestamp": 0}
                self.last_fetched[feed_url] = 0
        
        # Register feeds with server
        self._register_feeds_with_server()
    
    def _register_feeds_with_server(self):
        """
        Register all configured feeds with the server database.
        Creates Website entries for each feed.
        """
        if not self.server:
            return
        
        import uuid
        
        for feed in self.feeds_config:
            feed_url = feed.get("url")
            if not feed_url:
                continue
            
            try:
                # Check if website exists
                website_data = ray.get(self.server.get_website_by_rss.remote(feed_url))
                
                if website_data:
                    # Website exists, use its ID
                    website_id = website_data["id"]
                else:
                    # Create new website
                    website_data = {
                        "id": str(uuid.uuid4()),
                        "name": feed.get("name", "Unknown"),
                        "rss": feed_url,
                        "category": feed.get("category"),
                        "language": feed.get("language"),
                        "country": feed.get("country"),
                        "leaning": feed.get("leaning"),
                        "last_fetched": str(uuid.uuid4())
                    }
                    website_id = ray.get(self.server.add_website.remote(website_data))
                
                if website_id:
                    self.website_ids[feed_url] = website_id
                    
            except Exception as e:
                # Failed to register feed, continue with others
                pass
    
    def _should_refresh_cache(self, feed_url: str) -> bool:
        """
        Check if the cache for a feed should be refreshed.
        
        Args:
            feed_url (str): RSS feed URL
            
        Returns:
            bool: True if cache should be refreshed, False otherwise
        """
        current_time = time.time()
        last_fetch = self.last_fetched.get(feed_url, 0)
        return (current_time - last_fetch) > self.cache_duration
    
    def _fetch_feed(self, feed_url: str, feed_name: str = "Unknown") -> List[Dict]:
        """
        Fetch and parse articles from an RSS feed.
        
        Args:
            feed_url (str): RSS feed URL
            feed_name (str): Human-readable feed name
            
        Returns:
            list: List of article dictionaries with keys: title, summary, link, website_id
        """
        articles = []
        website_id = self.website_ids.get(feed_url)
        
        try:
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries[:20]:  # Limit to 20 most recent articles
                try:
                    article = {
                        "title": entry.get("title", "No title"),
                        "summary": entry.get("summary", entry.get("description", "No summary available")),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", "Unknown date"),
                        "source": feed_name,
                        "website_id": website_id  # Include website_id for database reference
                    }
                    articles.append(article)
                except Exception as e:
                    # Skip problematic entries
                    continue
                    
        except Exception as e:
            # Feed parsing failed, return empty list
            pass
        
        return articles
    
    def refresh_feed(self, feed_url: str) -> Dict:
        """
        Refresh the cache for a specific feed.
        
        Args:
            feed_url (str): RSS feed URL to refresh
            
        Returns:
            dict: Status dictionary with success/failure and article count
        """
        feed_config = next((f for f in self.feeds_config if f.get("url") == feed_url), None)
        
        if not feed_config:
            return {"success": False, "error": "Feed not configured", "count": 0}
        
        feed_name = feed_config.get("name", "Unknown")
        articles = self._fetch_feed(feed_url, feed_name)
        
        if articles:
            self.cached_news[feed_url] = {
                "articles": articles,
                "timestamp": time.time()
            }
            self.last_fetched[feed_url] = time.time()
            
            return {"success": True, "count": len(articles), "feed": feed_name}
        else:
            return {"success": False, "error": "No articles fetched", "count": 0}
    
    def refresh_all_feeds(self) -> Dict:
        """
        Refresh cache for all configured feeds that need updating.
        
        Returns:
            dict: Summary of refresh operation
        """
        results = {"refreshed": 0, "skipped": 0, "failed": 0, "total_articles": 0}
        
        for feed in self.feeds_config:
            feed_url = feed.get("url")
            if not feed_url:
                continue
                
            if self._should_refresh_cache(feed_url):
                result = self.refresh_feed(feed_url)
                if result["success"]:
                    results["refreshed"] += 1
                    results["total_articles"] += result["count"]
                else:
                    results["failed"] += 1
            else:
                results["skipped"] += 1
        
        return results
    
    def get_random_article(self, category: Optional[str] = None, 
                          language: Optional[str] = None) -> Optional[Dict]:
        """
        Get a random article from cached feeds.
        
        Optionally filter by category and/or language. If cache is stale,
        refreshes before returning an article.
        
        Args:
            category (str, optional): Filter by category (e.g., "tech", "politics")
            language (str, optional): Filter by language (e.g., "en", "es")
            
        Returns:
            dict or None: Article dictionary with keys: title, summary, link, source
                         Returns None if no articles available
        """
        # Refresh stale caches
        self.refresh_all_feeds()
        
        # Filter feeds by criteria
        eligible_feeds = []
        for feed in self.feeds_config:
            if category and feed.get("category") != category:
                continue
            if language and feed.get("language") != language:
                continue
            eligible_feeds.append(feed)
        
        if not eligible_feeds:
            # No matching feeds, use all feeds
            eligible_feeds = self.feeds_config
        
        # Collect all articles from eligible feeds
        all_articles = []
        for feed in eligible_feeds:
            feed_url = feed.get("url")
            if feed_url and feed_url in self.cached_news:
                articles = self.cached_news[feed_url].get("articles", [])
                all_articles.extend(articles)
        
        if not all_articles:
            return None
        
        # Return a random article
        return random.choice(all_articles)
    
    def save_article_to_db(self, article: Dict) -> Optional[str]:
        """
        Save an article to the database.
        
        Args:
            article (dict): Article dictionary with keys: title, summary, link, website_id
            
        Returns:
            str: Article ID if successful, None otherwise
        """
        if not self.server or not article:
            return None
        
        import uuid
        
        try:
            article_data = {
                "id": str(uuid.uuid4()),
                "title": article.get("title"),
                "summary": article.get("summary"),
                "website_id": article.get("website_id"),
                "link": article.get("link"),
                "fetched_on": str(uuid.uuid4())  # Using UUID as timestamp format
            }
            
            article_id = ray.get(self.server.add_article.remote(article_data))
            return article_id
            
        except Exception as e:
            # Failed to save article
            return None
    
    def get_feed_status(self) -> Dict:
        """
        Get status of all configured feeds.
        
        Returns:
            dict: Status information for each feed including last fetch time
                 and article count
        """
        status = {}
        current_time = time.time()
        
        for feed in self.feeds_config:
            feed_url = feed.get("url")
            feed_name = feed.get("name", "Unknown")
            
            if feed_url in self.cached_news:
                last_fetch = self.last_fetched.get(feed_url, 0)
                age_seconds = int(current_time - last_fetch)
                article_count = len(self.cached_news[feed_url].get("articles", []))
                
                status[feed_name] = {
                    "url": feed_url,
                    "articles": article_count,
                    "last_fetched": datetime.datetime.fromtimestamp(last_fetch).isoformat() if last_fetch > 0 else "Never",
                    "age_seconds": age_seconds,
                    "needs_refresh": self._should_refresh_cache(feed_url)
                }
        
        return status
