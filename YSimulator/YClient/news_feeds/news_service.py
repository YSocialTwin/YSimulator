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
        
        # Cache structure: {feed_url: {"articles": [...], "timestamp": int}}
        self.cached_news = {}
        self.last_fetched = {}
        
        # Initialize caches for all configured feeds
        for feed in self.feeds_config:
            feed_url = feed.get("url")
            if feed_url:
                self.cached_news[feed_url] = {"articles": [], "timestamp": 0}
                self.last_fetched[feed_url] = 0
    
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
            list: List of article dictionaries with keys: title, summary, link
        """
        articles = []
        try:
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries[:20]:  # Limit to 20 most recent articles
                try:
                    article = {
                        "title": entry.get("title", "No title"),
                        "summary": entry.get("summary", entry.get("description", "No summary available")),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", "Unknown date"),
                        "source": feed_name
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
