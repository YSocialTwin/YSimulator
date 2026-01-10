"""
Unit tests for DatabaseServiceAdapter batch methods.

This module ensures that the batch methods are properly exposed
through the DatabaseServiceAdapter layer.
"""

import unittest
import uuid
from unittest.mock import Mock

from sqlalchemy.orm import Session

from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware
from YSimulator.YServer.classes.models import Base
from YSimulator.YServer.database_adapter import DatabaseServiceAdapter
from YSimulator.YServer.repositories.sql_repository import (
    SQLFollowRepository,
    SQLInterestRepository,
    SQLPostRepository,
    SQLUserRepository,
)
from YSimulator.YServer.services.follow_service import FollowService
from YSimulator.YServer.services.interest_service import InterestService
from YSimulator.YServer.services.post_service import PostService
from YSimulator.YServer.services.user_service import UserService


class TestDatabaseAdapterBatchMethods(unittest.TestCase):
    """Test that DatabaseServiceAdapter properly exposes batch methods."""

    def setUp(self):
        """Set up test fixtures with in-memory SQLite database."""
        # Create an in-memory SQLite database for testing
        self.db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}

        # Initialize database middleware
        self.db = DatabaseMiddleware(db_config=self.db_config, config_path=".", redis_config=None)

        # Create tables
        Base.metadata.create_all(self.db.engine)

        # Create mock logger
        self.mock_logger = Mock()

        # Initialize repositories
        user_repo = SQLUserRepository(self.db.engine, self.mock_logger)
        post_repo = SQLPostRepository(self.db.engine, self.mock_logger)
        follow_repo = SQLFollowRepository(self.db.engine, self.mock_logger)
        interest_repo = SQLInterestRepository(self.db.engine, self.mock_logger)

        # Initialize services
        user_service = UserService(user_repo, self.mock_logger)
        post_service = PostService(post_repo, interest_repo, self.mock_logger)
        follow_service = FollowService(follow_repo, self.mock_logger)
        interest_service = InterestService(interest_repo, self.mock_logger)

        # Create a minimal adapter (only with services we need for testing)
        self.adapter = DatabaseServiceAdapter(
            user_service=user_service,
            post_service=post_service,
            follow_service=follow_service,
            interest_service=interest_service,
            article_service=Mock(),
            image_service=Mock(),
            content_service=Mock(),
            simulation_service=Mock(),
            metadata_service=Mock(),
            mention_service=Mock(),
            logger=self.mock_logger,
        )

        # Create test round
        self.round_id = str(uuid.uuid4())

    def test_adapter_has_add_or_get_interests_batch(self):
        """Test that adapter exposes add_or_get_interests_batch method."""
        self.assertTrue(hasattr(self.adapter, "add_or_get_interests_batch"))
        self.assertTrue(callable(self.adapter.add_or_get_interests_batch))

    def test_adapter_has_add_user_interests_batch(self):
        """Test that adapter exposes add_user_interests_batch method."""
        self.assertTrue(hasattr(self.adapter, "add_user_interests_batch"))
        self.assertTrue(callable(self.adapter.add_user_interests_batch))

    def test_adapter_has_add_agent_opinions_batch(self):
        """Test that adapter exposes add_agent_opinions_batch method."""
        self.assertTrue(hasattr(self.adapter, "add_agent_opinions_batch"))
        self.assertTrue(callable(self.adapter.add_agent_opinions_batch))

    def test_adapter_add_or_get_interests_batch_works(self):
        """Test that add_or_get_interests_batch works through adapter."""
        interest_names = ["Technology", "Science", "Politics"]

        # Call through adapter
        result = self.adapter.add_or_get_interests_batch(interest_names)

        # Verify result
        self.assertEqual(len(result), 3)
        self.assertTrue(all(name in result for name in interest_names))

    def test_adapter_add_user_interests_batch_works(self):
        """Test that add_user_interests_batch works through adapter."""
        # Create interests first
        interest_names = ["Technology", "Science"]
        interest_map = self.adapter.add_or_get_interests_batch(interest_names)

        # Prepare user interests data
        user_id = str(uuid.uuid4())
        user_interests = [
            {
                "user_id": user_id,
                "interest_id": interest_map["Technology"],
                "round_id": self.round_id,
            },
            {
                "user_id": user_id,
                "interest_id": interest_map["Science"],
                "round_id": self.round_id,
            },
        ]

        # Call through adapter
        added_count = self.adapter.add_user_interests_batch(user_interests)

        # Verify result
        self.assertEqual(added_count, 2)

    def test_adapter_add_agent_opinions_batch_works(self):
        """Test that add_agent_opinions_batch works through adapter."""
        # Create interests first
        interest_names = ["Climate Change", "Healthcare"]
        interest_map = self.adapter.add_or_get_interests_batch(interest_names)

        # Prepare agent opinions data
        agent_id = str(uuid.uuid4())
        agent_opinions = [
            {
                "agent_id": agent_id,
                "tid": self.round_id,
                "topic_id": interest_map["Climate Change"],
                "opinion": 0.8,
                "id_interacted_with": None,
                "id_post": None,
            },
            {
                "agent_id": agent_id,
                "tid": self.round_id,
                "topic_id": interest_map["Healthcare"],
                "opinion": -0.5,
                "id_interacted_with": None,
                "id_post": None,
            },
        ]

        # Call through adapter
        added_count = self.adapter.add_agent_opinions_batch(agent_opinions)

        # Verify result
        self.assertEqual(added_count, 2)

    def test_adapter_batch_methods_integrate_correctly(self):
        """Test that all batch methods work together through adapter."""
        # Step 1: Batch create interests
        interest_names = ["Tech", "Science", "Sports"]
        interest_map = self.adapter.add_or_get_interests_batch(interest_names)
        self.assertEqual(len(interest_map), 3)

        # Step 2: Batch add user interests
        user_id = str(uuid.uuid4())
        user_interests = [
            {
                "user_id": user_id,
                "interest_id": interest_map["Tech"],
                "round_id": self.round_id,
            }
        ]
        interests_added = self.adapter.add_user_interests_batch(user_interests)
        self.assertEqual(interests_added, 1)

        # Step 3: Batch add agent opinions
        agent_id = str(uuid.uuid4())
        opinions = [
            {
                "agent_id": agent_id,
                "tid": self.round_id,
                "topic_id": interest_map["Tech"],
                "opinion": 0.7,
                "id_interacted_with": None,
                "id_post": None,
            }
        ]
        opinions_added = self.adapter.add_agent_opinions_batch(opinions)
        self.assertEqual(opinions_added, 1)


if __name__ == "__main__":
    unittest.main()
