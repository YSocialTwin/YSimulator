"""
Mention service for mention and reply tracking operations.

This service encapsulates all mention-related business operations.
"""

import logging
from typing import Any, Dict, List

from sqlalchemy import MetaData, Table, inspect, select
from sqlalchemy.orm import Session

from YSimulator.YServer.repositories.base_repository import PostRepository


class MentionService:
    """Service for mention and reply business logic."""

    def __init__(
        self,
        post_repository: PostRepository,
        engine=None,
        logger: logging.Logger = None,
    ):
        """
        Initialize mention service.

        Args:
            post_repository: Repository for mention operations
            logger: Logger instance
        """
        self.post_repo = post_repository
        self.engine = engine
        self.logger = logger or logging.getLogger(__name__)

    def add_mention(self, post_id: str, mentioned_user_id: str) -> bool:
        """
        Add a mention to a post.

        Args:
            post_id: Post ID
            mentioned_user_id: ID of mentioned user

        Returns:
            True if successful, False otherwise
        """
        try:
            return self.post_repo.add_mention(post_id, mentioned_user_id)
        except Exception as e:
            self.logger.error(f"Error adding mention: {e}")
            return False

    def get_unreplied_mentions(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get unreplied mentions for a user.

        Args:
            user_id: User ID

        Returns:
            List of unreplied mention dicts
        """
        try:
            mentions = self.post_repo.get_unreplied_mentions(user_id)
            return self._filter_shadow_banned_mentions(mentions)
        except Exception as e:
            self.logger.error(f"Error getting unreplied mentions: {e}")
            return []

    def mark_mention_replied(self, post_id: str, mentioned_user_id: str) -> bool:
        """
        Mark a mention as replied.

        Args:
            post_id: Post ID
            mentioned_user_id: ID of mentioned user

        Returns:
            True if successful, False otherwise
        """
        try:
            return self.post_repo.mark_mention_replied(post_id, mentioned_user_id)
        except Exception as e:
            self.logger.error(f"Error marking mention as replied: {e}")
            return False

    def _filter_shadow_banned_mentions(
        self, mentions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        if not mentions or self.engine is None:
            return mentions
        try:
            inspector = inspect(self.engine)
            if "shadow_ban" not in inspector.get_table_names():
                return mentions
            if "post" not in inspector.get_table_names() or "rounds" not in inspector.get_table_names():
                return mentions

            metadata = MetaData()
            shadow_ban = Table("shadow_ban", metadata, autoload_with=self.engine)
            post = Table("post", metadata, autoload_with=self.engine)
            rounds = Table("rounds", metadata, autoload_with=self.engine)

            with Session(self.engine) as session:
                current_round_id = session.execute(
                    select(rounds.c.id).order_by(rounds.c.id.desc()).limit(1)
                ).scalar()
                if current_round_id is None:
                    return mentions

                active_banned_user_ids = {
                    row[0]
                    for row in session.execute(
                        select(shadow_ban.c.uid)
                        .where(shadow_ban.c.start_tid <= int(current_round_id))
                        .where(
                            (shadow_ban.c.duration.is_(None))
                            | ((shadow_ban.c.start_tid + shadow_ban.c.duration) >= int(current_round_id))
                        )
                    ).all()
                }
                if not active_banned_user_ids:
                    return mentions

                visible_mentions: List[Dict[str, Any]] = []
                for mention in mentions:
                    post_id = mention.get("post_id")
                    if not post_id:
                        visible_mentions.append(mention)
                        continue
                    author_id = session.execute(
                        select(post.c.user_id).where(post.c.id == post_id).limit(1)
                    ).scalar()
                    if author_id in active_banned_user_ids:
                        continue
                    visible_mentions.append(mention)
                return visible_mentions
        except Exception as e:
            self.logger.warning(f"Shadow-ban mention filter fallback: {e}")
            return mentions
