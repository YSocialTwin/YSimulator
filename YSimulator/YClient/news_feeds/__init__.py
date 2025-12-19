"""
News feeds package for YSimulator.

This package provides RSS feed integration for the simulation:
- news_service: Ray actor for async news fetching
- feed_reader: Original feed parsing utilities (legacy)
"""

from YSimulator.YClient.news_feeds.news_service import NewsFeedService

__all__ = [
    "NewsFeedService",
]
