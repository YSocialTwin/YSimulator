"""
Mention service for mention and reply tracking operations.

This service encapsulates all mention-related business operations.
"""

import logging
from typing import Any, Dict, List

from sqlalchemy import MetaData, Table, cast, inspect, select
from sqlalchemy.types import Integer
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

    def get_users_with_unreplied_mentions(self, user_ids: List[str]) -> List[str]:
        """Return the subset of user_ids that currently have unreplied mentions."""
        if not user_ids:
            return []
        try:
            if hasattr(self.post_repo, "get_users_with_unreplied_mentions"):
                users = self.post_repo.get_users_with_unreplied_mentions(user_ids)
                return [str(user_id) for user_id in users if user_id]

            matched_users = []
            for user_id in user_ids:
                mentions = self.get_unreplied_mentions(user_id)
                if mentions:
                    matched_users.append(str(user_id))
            return matched_users
        except Exception as e:
            self.logger.error(f"Error getting users with unreplied mentions: {e}")
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
                current_round = session.execute(
                    select(rounds.c.id, rounds.c.day, rounds.c.hour)
                    .order_by(rounds.c.day.desc(), rounds.c.hour.desc())
                    .limit(1)
                ).first()
                if current_round is None:
                    return mentions
                current_round_id = current_round[0]

                shadow_ban_columns = {column.name for column in shadow_ban.c}
                active_banned_user_ids = set()
                if "start_tid" in shadow_ban_columns:
                    start_tid_type = getattr(shadow_ban.c.start_tid.type, "python_type", None)
                    if start_tid_type is int:
                        active_banned_user_ids = {
                            row[0]
                            for row in session.execute(
                                select(shadow_ban.c.uid)
                                .where(cast(shadow_ban.c.start_tid, Integer) <= int(current_round_id))
                                .where(
                                    (shadow_ban.c.duration.is_(None))
                                    | (
                                        cast(shadow_ban.c.start_tid, Integer) + shadow_ban.c.duration
                                        >= int(current_round_id)
                                    )
                                )
                            ).all()
                        }
                    else:
                        start_rounds = rounds.alias("start_rounds")
                        active_banned_user_ids = {
                            row[0]
                            for row in session.execute(
                                select(shadow_ban.c.uid)
                                .select_from(
                                    shadow_ban.outerjoin(
                                        start_rounds, start_rounds.c.id == shadow_ban.c.start_tid
                                    )
                                )
                                .where(
                                    (
                                        (start_rounds.c.day < current_round.day)
                                        | (
                                            (start_rounds.c.day == current_round.day)
                                            & (start_rounds.c.hour <= current_round.hour)
                                        )
                                    )
                                    | (shadow_ban.c.start_tid == current_round_id)
                                )
                                .where(
                                    (shadow_ban.c.duration.is_(None))
                                    | (
                                        (
                                            ((start_rounds.c.day * 24) + start_rounds.c.hour)
                                            + shadow_ban.c.duration
                                        )
                                        >= ((current_round.day * 24) + current_round.hour)
                                    )
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
