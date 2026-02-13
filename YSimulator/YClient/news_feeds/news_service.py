"""
News Feed Service - Ray Actor for Async News Fetching

This module provides a Ray-based asynchronous news feed service for the Y social
network simulation. It handles fetching articles from RSS feeds, caching them,
and providing news content for agent actions.

The service is designed to work asynchronously similar to LLMService to avoid
blocking simulation execution.
"""

import datetime
import logging
import random
import time
from typing import Any, Dict, List, Optional

import feedparser
import ray


def _get_llm_actor(llm_handle: Any) -> Any:
    """
    Get the appropriate LLM actor from handle.

    If llm_handle is a LLMLoadBalancer, uses the first actor.
    Otherwise returns llm_handle directly (single actor case).

    Args:
        llm_handle: Either a Ray actor handle or a LLMLoadBalancer instance

    Returns:
        Ray actor handle for LLM service
    """
    # Check if llm_handle is a load balancer by checking its class name
    if llm_handle.__class__.__name__ in ("LLMLoadBalancer", "LLMActorPool"):
        # Use first actor for image descriptions (not agent-specific)
        return llm_handle.get_all_actors()[0]
    # Direct actor handle (including Ray actors)
    return llm_handle


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
        logger: Logger instance for this service
    """

    def __init__(self, feeds_config: Optional[Dict] = None, llm_service=None):
        """
        Initialize the NewsFeedService actor.

        Feeds are now registered dynamically by page agents via register_page_feed().
        The feeds_config parameter is kept for backward compatibility but defaults to empty.

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
            llm_service: Ray actor reference for LLMService (for image descriptions)
        """
        # Initialize logger
        self.logger = logging.getLogger("YSimulator.NewsFeedService")

        # Load configuration with defaults
        # Note: Feeds are now registered by page agents, so we start with an empty list
        if feeds_config is None:
            feeds_config = {
                "feeds": [],  # Start empty - page agents will register their feeds
                "cache_duration": 3600,  # 1 hour
            }

        self.feeds_config = feeds_config.get("feeds", [])
        self.cache_duration = feeds_config.get("cache_duration", 3600)
        self.llm_service = llm_service  # Store LLM service reference for image descriptions

        # Get server actor reference
        try:
            self.server = ray.get_actor("Orchestrator")
        except ValueError:
            # Orchestrator actor not found - this is expected if news service starts before server
            self.logger.warning("Orchestrator actor not yet available, will retry later")
            self.server = None

        # Cache structure: {feed_url: {"articles": [...], "timestamp": int, "website_id": str}}
        self.cached_news = {}
        self.last_fetched = {}
        self.website_ids = {}  # Map feed_url to website_id (page agent id)

        # Initialize caches for all configured feeds (if any)
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
                        "last_fetched": str(uuid.uuid4()),
                    }
                    website_id = ray.get(self.server.add_website.remote(website_data))

                if website_id:
                    self.website_ids[feed_url] = website_id

            except Exception:
                # Failed to register feed, continue with others
                pass

    def register_page_feed(self, feed_url: str, page_id: str) -> bool:
        """
        Register a page agent's feed with the news service.
        This is called when a page agent is registered to enable its feed.

        Args:
            feed_url (str): RSS feed URL for the page
            page_id (str): Page agent's user ID (also the website ID)

        Returns:
            bool: True if successfully registered, False otherwise
        """
        if not feed_url:
            return False

        # Add feed to feeds_config if not already present
        # This is needed for refresh_feed to work properly
        if not any(f.get("url") == feed_url for f in self.feeds_config):
            feed_config = {
                "url": feed_url,
                "name": f"Page_{page_id}",  # Use page_id as feed name
                "category": "page",
                "language": "en",  # Default language
            }
            self.feeds_config.append(feed_config)

        # Initialize cache for this feed if not already present
        if feed_url not in self.cached_news:
            self.cached_news[feed_url] = {"articles": [], "timestamp": 0}
            self.last_fetched[feed_url] = 0

        # Store the website_id (which is the page_id)
        self.website_ids[feed_url] = page_id

        # Try to fetch initial articles
        try:
            self.refresh_feed(feed_url)
            return True
        except Exception:
            # Log specific error
            return False

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
            list: List of article dictionaries with keys: title, summary, link, website_id, images
        """
        articles = []
        website_id = self.website_ids.get(feed_url)
        total_images_found = 0

        try:
            feed = feedparser.parse(feed_url)
            self.logger.info(f"Fetching from {feed_name}: found {len(feed.entries)} entries")

            for entry in feed.entries[:20]:  # Limit to 20 most recent articles
                try:
                    # Extract image URLs from the entry
                    image_urls = self._extract_images_from_entry(entry)

                    if image_urls:
                        total_images_found += len(image_urls)
                        self.logger.debug(
                            f"Article '{entry.get( 'title', 'No title')[ :50]}' has {len(image_urls)}image(s)"
                        )

                    article = {
                        "title": entry.get("title", "No title"),
                        "summary": entry.get(
                            "summary", entry.get("description", "No summary available")
                        ),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", "Unknown date"),
                        "source": feed_name,
                        "website_id": website_id,  # Include website_id for database reference
                        "image_urls": image_urls,  # Add image URLs to article
                    }
                    articles.append(article)
                except Exception as e:
                    # Skip problematic entries
                    self.logger.warning(f"Failed to process entry: {e}")
                    continue

        except Exception as e:
            # Feed parsing failed, return empty list
            self.logger.error(f"Failed to parse feed {feed_url}: {e}")

        self.logger.info(
            f"Feed {feed_name}: {len(articles)} articles, {total_images_found} total images"
        )
        return articles

    def _extract_images_from_entry(self, entry) -> List[str]:
        """
        Extract image URLs from an RSS feed entry.

        Images can be found in various fields:
        - media_content
        - media_thumbnail
        - enclosures

        Args:
            entry: RSS feed entry from feedparser

        Returns:
            list: List of image URLs found in the entry
        """
        image_urls = []

        # Log what fields are available for debugging
        available_fields = []
        if hasattr(entry, "media_content") and entry.media_content:
            available_fields.append("media_content")
        if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
            available_fields.append("media_thumbnail")
        if hasattr(entry, "enclosures") and entry.enclosures:
            available_fields.append("enclosures")

        if available_fields:
            self.logger.debug(f"Entry has image fields: {', '.join(available_fields)}")

        # Check media_content
        if hasattr(entry, "media_content") and entry.media_content:
            for media in entry.media_content:
                media_type = media.get("type", "")
                self.logger.debug(f"Checking media_content item: type={media_type}")
                if media_type.startswith("image/"):
                    url = media.get("url")
                    if url and url not in image_urls:
                        image_urls.append(url)
                        self.logger.debug(f"Found image in media_content: {url[:80]}")

        # Check media_thumbnail
        if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
            for thumb in entry.media_thumbnail:
                url = thumb.get("url")
                if url and url not in image_urls:
                    image_urls.append(url)
                    self.logger.debug(f"Found image in media_thumbnail: {url[:80]}")

        # Check enclosures
        if hasattr(entry, "enclosures") and entry.enclosures:
            for enclosure in entry.enclosures:
                enclosure_type = enclosure.get("type", "")
                self.logger.debug(f"Checking enclosure item: type={enclosure_type}")
                if enclosure_type.startswith("image/"):
                    url = enclosure.get("href")
                    if url and url not in image_urls:
                        image_urls.append(url)
                        self.logger.debug(f"Found image in enclosures: {url[:80]}")

        if not image_urls and not available_fields:
            self.logger.debug(
                "Entry has no image-related fields (media_content, media_thumbnail, enclosures)"
            )

        return image_urls

    def refresh_feed(self, feed_url: str) -> Dict:
        """
        Refresh the cache for a specific feed.

        Args:
            feed_url (str): RSS feed URL to refresh

        Returns:
            dict: Status dictionary with success/failure and article count
        """
        self.logger.info(f"refresh_feed called for: {feed_url[:80]}")

        feed_config = next((f for f in self.feeds_config if f.get("url") == feed_url), None)

        if not feed_config:
            self.logger.error(f"Feed not configured: {feed_url[:80]}")
            return {"success": False, "error": "Feed not configured", "count": 0}

        feed_name = feed_config.get("name", "Unknown")
        self.logger.info(f"Fetching feed '{feed_name}' from {feed_url[:80]}")
        articles = self._fetch_feed(feed_url, feed_name)

        if articles:
            self.cached_news[feed_url] = {"articles": articles, "timestamp": time.time()}
            self.last_fetched[feed_url] = time.time()

            self.logger.info(f"Feed '{feed_name}' cached: {len(articles)} articles")
            return {"success": True, "count": len(articles), "feed": feed_name}
        else:
            self.logger.warning(f"No articles fetched from feed '{feed_name}'")
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

    def get_random_article(
        self, category: Optional[str] = None, language: Optional[str] = None
    ) -> Optional[Dict]:
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

    def get_article_from_feed(self, feed_url: str) -> Optional[Dict]:
        """
        Get a random article from a specific feed URL.
        Used by page agents to get articles from their assigned feed.

        Args:
            feed_url (str): RSS feed URL

        Returns:
            dict or None: Article dictionary with keys: title, summary, link, source, website_id, image_urls
                         Returns None if no articles available
        """
        self.logger.info(f"get_article_from_feed called for: {feed_url[:80]}")

        # Refresh cache if stale
        if self._should_refresh_cache(feed_url):
            self.logger.info("Cache is stale, refreshing feed")
            self.refresh_feed(feed_url)
        else:
            self.logger.debug("Using cached articles")

        # Get articles from this specific feed
        if feed_url in self.cached_news:
            articles = self.cached_news[feed_url].get("articles", [])
            self.logger.debug(f"Feed has {len(articles)} cached articles")

            if articles:
                article = random.choice(articles)
                image_count = len(article.get("image_urls", []))
                self.logger.info(
                    f"Returning article: '{article.get( 'title', 'NO TITLE')[ :50]}' with {image_count}image(s)"
                )
                return article
            else:
                self.logger.warning("No articles available in cache")
        else:
            self.logger.warning("Feed URL not in cached_news dictionary")

        return None

    def save_article_to_db(self, article: Dict) -> Optional[str]:
        """
        Save an article to the database along with its images.

        Args:
            article (dict): Article dictionary with keys: title, summary, link, website_id, image_urls

        Returns:
            str: Article ID if successful, None otherwise
        """
        if not self.server:
            self.logger.error("No server connection for saving article")
            return None

        if not article:
            self.logger.error("No article data provided")
            return None

        import uuid

        try:
            article_data = {
                "id": str(uuid.uuid4()),
                "title": article.get("title"),
                "summary": article.get("summary"),
                "website_id": article.get("website_id"),
                "link": article.get("link"),
                "fetched_on": str(uuid.uuid4()),  # Using UUID as timestamp format
            }

            # Debug logging
            self.logger.info(
                f"Saving article: title='{article_data['title'][:50]}...', website_id={article_data['website_id']}"
            )

            article_id = ray.get(self.server.add_article.remote(article_data))

            if article_id:
                self.logger.info(f"Article saved successfully: id={article_id}")

                # Process and save images if any
                image_urls = article.get("image_urls", [])
                self.logger.info(f"Article has {len(image_urls)} image(s) to process")

                if image_urls:
                    if self.llm_service:
                        self.logger.info(f"Starting image processing for article {article_id}")
                        self._process_and_save_images(article_id, image_urls)
                    else:
                        self.logger.warning(
                            f"LLM service not available, skipping {len(image_urls)} image(s)"
                        )
                else:
                    self.logger.info("No images to process for this article")
            else:
                self.logger.error("Failed to save article (server returned None)")

            return article_id

        except Exception as e:
            # Failed to save article - log the error
            self.logger.error(f"Exception while saving article: {e}")
            import traceback

            traceback.print_exc()
            return None

    def _process_and_save_images(self, article_id: str, image_urls: List[str]):
        """
        Process images by getting descriptions from LLM and saving to database.
        
        - Limits to maximum 3 images per article
        - Checks if image URL already exists before requesting LLM description
        - Reuses existing descriptions for duplicate URLs

        Args:
            article_id: UUID of the article these images belong to
            image_urls: List of image URLs to process
        """
        import uuid

        # Check if LLM service is available
        if not self.llm_service:
            self.logger.warning("LLM service not available, skipping image descriptions")
            return

        # Limit to 3 images per article
        MAX_IMAGES_PER_ARTICLE = 3
        if len(image_urls) > MAX_IMAGES_PER_ARTICLE:
            self.logger.info(
                f"Article has {len(image_urls)} images, limiting to {MAX_IMAGES_PER_ARTICLE}"
            )
            image_urls = image_urls[:MAX_IMAGES_PER_ARTICLE]

        self.logger.info(f"Processing {len(image_urls)} image(s) for article {article_id}")
        successful_saves = 0
        reused_existing = 0
        failed_descriptions = 0
        failed_saves = 0

        for idx, image_url in enumerate(image_urls, 1):
            try:
                # Check if image already exists in database
                self.logger.info(
                    f"[{idx}/{len(image_urls)}] Checking if image already exists: {image_url[:80]}..."
                )
                existing_image = ray.get(self.server.get_image_by_url.remote(image_url))
                
                if existing_image:
                    # Image already exists, reuse it by creating a new entry with same URL and description
                    self.logger.info(
                        f"[{idx}/{len(image_urls)}] ✓ Found existing image (id={existing_image['id']}), "
                        f"reusing description: {existing_image['description'][:100]}..."
                    )
                    
                    # Create new image entry for this article with the existing description
                    image_data = {
                        "id": str(uuid.uuid4()),
                        "url": image_url,
                        "description": existing_image["description"],
                        "article_id": article_id,
                    }
                    
                    self.logger.info(f"[{idx}/{len(image_urls)}] Saving reused image to database...")
                    image_id = ray.get(self.server.add_image.remote(image_data))
                    
                    if image_id:
                        reused_existing += 1
                        successful_saves += 1
                        self.logger.info(
                            f"[{idx}/{len(image_urls)}] ✓ Image saved successfully with reused description: id={image_id}"
                        )
                    else:
                        failed_saves += 1
                        self.logger.info(
                            f"[{idx}/{len(image_urls)}] ✗ WARNING: Failed to save image to database"
                        )
                    continue

                # Image doesn't exist, get description from LLM
                self.logger.info(
                    f"[{idx}/{len(image_urls)}] Requesting new description from LLM for image: {image_url[:80]}..."
                )
                # Get the appropriate LLM actor (handles LLMLoadBalancer case)
                llm_actor = _get_llm_actor(self.llm_service)
                description = ray.get(llm_actor.describe_image.remote(image_url))

                if description:
                    self.logger.info(
                        f"[{idx}/{len(image_urls)}] Got description ({len(description)} chars): {description[:100]}..."
                    )

                    # Save image to database
                    image_data = {
                        "id": str(uuid.uuid4()),
                        "url": image_url,
                        "description": description,
                        "article_id": article_id,
                    }

                    self.logger.info(f"[{idx}/{len(image_urls)}] Saving new image to database...")
                    image_id = ray.get(self.server.add_image.remote(image_data))

                    if image_id:
                        successful_saves += 1
                        self.logger.info(
                            f"[{idx}/{len(image_urls)}] ✓ Image saved successfully: id={image_id}"
                        )
                    else:
                        failed_saves += 1
                        self.logger.info(
                            f"[{idx}/{len(image_urls)}] ✗ WARNING: Failed to save image to database"
                        )
                else:
                    failed_descriptions += 1
                    self.logger.info(
                        f"[{idx}/{len(image_urls)}] ✗ WARNING: No description returned from LLM for image"
                    )

            except Exception as e:
                # Log error but continue with other images
                failed_descriptions += 1
                self.logger.info(
                    f"[{idx}/{len(image_urls)}] ✗ ERROR: Failed to process image {image_url[:80]}: {e}"
                )
                import traceback

                traceback.print_exc()
                continue

        # Summary logging
        self.logger.info(f"Image processing summary for article {article_id}:")
        self.logger.info(f"  - Total images: {len(image_urls)}")
        self.logger.info(f"  - Successfully saved: {successful_saves}")
        self.logger.info(f"  - Reused existing descriptions: {reused_existing}")
        self.logger.info(f"  - New descriptions from LLM: {successful_saves - reused_existing}")
        self.logger.info(f"  - Failed descriptions: {failed_descriptions}")
        self.logger.info(f"  - Failed saves: {failed_saves}")

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
                    "last_fetched": (
                        datetime.datetime.fromtimestamp(last_fetch).isoformat()
                        if last_fetch > 0
                        else "Never"
                    ),
                    "age_seconds": age_seconds,
                    "needs_refresh": self._should_refresh_cache(feed_url),
                }

        return status
