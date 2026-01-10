"""
Unit tests for batch agent interests and opinions initialization.

This module tests the optimization added for batched database writes
during agent population loading, ensuring compliance with YSocial patterns.
"""

import unittest
import uuid
from typing import List
from unittest.mock import Mock, patch

from sqlalchemy.orm import Session

from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware
from YSimulator.YServer.classes.models import Agent_Opinion, Base, Interest, UserInterest
from YSimulator.YServer.interests_modeling.interest_manager import InterestManager
from YSimulator.YServer.repositories.sql_repository import SQLInterestRepository
from YSimulator.YServer.services.interest_service import InterestService


class TestBatchInterestOperations(unittest.TestCase):
    """Test batched interest and opinion initialization operations."""

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

        # Initialize repository and service
        self.repository = SQLInterestRepository(self.db.engine, self.mock_logger)
        self.interest_service = InterestService(self.repository, self.mock_logger)

        # Initialize interest manager
        self.interest_manager = InterestManager(self.repository, attention_window=336)

        # Create test round
        self.round_id = str(uuid.uuid4())

    def test_add_or_get_interests_batch_new_interests(self):
        """Test batch creation of new interests."""
        interest_names = ["Technology", "Science", "Politics", "Sports"]

        # Add interests in batch
        result = self.repository.add_or_get_interests_batch(interest_names)

        # Verify all interests were created
        self.assertEqual(len(result), 4)
        self.assertTrue(all(name in result for name in interest_names))

        # Verify interests are in database
        with Session(self.db.engine) as session:
            interests = session.query(Interest).all()
            self.assertEqual(len(interests), 4)
            interest_names_db = {interest.interest for interest in interests}
            self.assertEqual(interest_names_db, set(interest_names))

    def test_add_or_get_interests_batch_existing_interests(self):
        """Test batch retrieval of existing interests."""
        interest_names = ["Technology", "Science"]

        # Create interests first
        first_result = self.repository.add_or_get_interests_batch(interest_names)

        # Try to add same interests again
        second_result = self.repository.add_or_get_interests_batch(interest_names)

        # Verify same IDs are returned
        self.assertEqual(first_result, second_result)

        # Verify no duplicates in database
        with Session(self.db.engine) as session:
            interests = session.query(Interest).all()
            self.assertEqual(len(interests), 2)

    def test_add_or_get_interests_batch_mixed(self):
        """Test batch operation with mix of existing and new interests."""
        # Create some interests first
        existing_names = ["Technology", "Science"]
        self.repository.add_or_get_interests_batch(existing_names)

        # Add batch with both existing and new interests
        mixed_names = ["Technology", "Science", "Politics", "Sports"]
        result = self.repository.add_or_get_interests_batch(mixed_names)

        # Verify all interests are returned
        self.assertEqual(len(result), 4)

        # Verify database has exactly 4 interests
        with Session(self.db.engine) as session:
            interests = session.query(Interest).all()
            self.assertEqual(len(interests), 4)

    def test_add_user_interests_batch(self):
        """Test batch insertion of user interests."""
        # Create test users (agent IDs)
        user1_id = str(uuid.uuid4())
        user2_id = str(uuid.uuid4())

        # Create interests
        interest_names = ["Technology", "Science"]
        interest_map = self.repository.add_or_get_interests_batch(interest_names)

        # Prepare user interests data
        user_interests = [
            {
                "user_id": user1_id,
                "interest_id": interest_map["Technology"],
                "round_id": self.round_id,
            },
            {
                "user_id": user1_id,
                "interest_id": interest_map["Science"],
                "round_id": self.round_id,
            },
            {
                "user_id": user2_id,
                "interest_id": interest_map["Technology"],
                "round_id": self.round_id,
            },
        ]

        # Batch insert
        added_count = self.repository.add_user_interests_batch(user_interests)

        # Verify count
        self.assertEqual(added_count, 3)

        # Verify in database
        with Session(self.db.engine) as session:
            user_interests_db = session.query(UserInterest).all()
            self.assertEqual(len(user_interests_db), 3)

            # Verify user1 has 2 interests
            user1_interests = session.query(UserInterest).filter_by(user_id=user1_id).all()
            self.assertEqual(len(user1_interests), 2)

    def test_add_agent_opinions_batch(self):
        """Test batch insertion of agent opinions."""
        # Create test agents
        agent1_id = str(uuid.uuid4())
        agent2_id = str(uuid.uuid4())

        # Create topics
        topic_names = ["Climate Change", "Healthcare"]
        topic_map = self.repository.add_or_get_interests_batch(topic_names)

        # Prepare agent opinions data
        agent_opinions = [
            {
                "agent_id": agent1_id,
                "tid": self.round_id,
                "topic_id": topic_map["Climate Change"],
                "opinion": 0.8,
                "id_interacted_with": None,
                "id_post": None,
            },
            {
                "agent_id": agent1_id,
                "tid": self.round_id,
                "topic_id": topic_map["Healthcare"],
                "opinion": -0.5,
                "id_interacted_with": None,
                "id_post": None,
            },
            {
                "agent_id": agent2_id,
                "tid": self.round_id,
                "topic_id": topic_map["Climate Change"],
                "opinion": 0.3,
                "id_interacted_with": None,
                "id_post": None,
            },
        ]

        # Batch insert
        added_count = self.repository.add_agent_opinions_batch(agent_opinions)

        # Verify count
        self.assertEqual(added_count, 3)

        # Verify in database
        with Session(self.db.engine) as session:
            opinions_db = session.query(Agent_Opinion).all()
            self.assertEqual(len(opinions_db), 3)

            # Verify agent1 has 2 opinions
            agent1_opinions = session.query(Agent_Opinion).filter_by(agent_id=agent1_id).all()
            self.assertEqual(len(agent1_opinions), 2)

    def test_add_user_interests_batch_large_dataset(self):
        """Test batch insertion with large dataset to verify batching works."""
        # Create a large number of interests and user_interest entries
        num_interests = 100
        num_users = 50
        entries_per_user = 10

        # Create interests
        interest_names = [f"Interest_{i}" for i in range(num_interests)]
        interest_map = self.repository.add_or_get_interests_batch(interest_names)

        # Prepare large user interests dataset
        user_interests = []
        for user_idx in range(num_users):
            user_id = str(uuid.uuid4())
            # Each user gets entries_per_user interests
            for entry_idx in range(entries_per_user):
                interest_name = f"Interest_{(user_idx + entry_idx) % num_interests}"
                user_interests.append(
                    {
                        "user_id": user_id,
                        "interest_id": interest_map[interest_name],
                        "round_id": self.round_id,
                    }
                )

        total_entries = num_users * entries_per_user

        # Batch insert with smaller batch size
        added_count = self.repository.add_user_interests_batch(user_interests, batch_size=100)

        # Verify count
        self.assertEqual(added_count, total_entries)

        # Verify in database
        with Session(self.db.engine) as session:
            user_interests_db = session.query(UserInterest).all()
            self.assertEqual(len(user_interests_db), total_entries)

    def test_interest_manager_batch_initialization(self):
        """Test InterestManager batch initialization of agent interests."""
        # Prepare test data
        agent1_id = str(uuid.uuid4())
        agent2_id = str(uuid.uuid4())

        agents_data = [
            {
                "agent_id": agent1_id,
                "interests": [["Technology", "Science"], [3, 2]],
            },
            {
                "agent_id": agent2_id,
                "interests": [["Politics", "Sports"], [5, 1]],
            },
        ]

        # Batch initialize
        results = self.interest_manager.initialize_agent_interests_batch(agents_data, self.round_id)

        # Verify results
        self.assertTrue(results[agent1_id])
        self.assertTrue(results[agent2_id])

        # Verify interests are in memory
        agent_interests = self.interest_manager.get_agent_interests()
        self.assertIn(agent1_id, agent_interests)
        self.assertIn(agent2_id, agent_interests)
        self.assertEqual(agent_interests[agent1_id]["topics"], ["Technology", "Science"])
        self.assertEqual(agent_interests[agent1_id]["counts"], [3, 2])

        # Verify user_interest entries in database
        # Agent1 should have 3 + 2 = 5 entries
        # Agent2 should have 5 + 1 = 6 entries
        with Session(self.db.engine) as session:
            agent1_entries = session.query(UserInterest).filter_by(user_id=agent1_id).all()
            agent2_entries = session.query(UserInterest).filter_by(user_id=agent2_id).all()
            self.assertEqual(len(agent1_entries), 5)
            self.assertEqual(len(agent2_entries), 6)

    def test_interest_manager_batch_initialization_invalid_data(self):
        """Test batch initialization handles invalid data gracefully."""
        agent1_id = str(uuid.uuid4())
        agent2_id = str(uuid.uuid4())

        agents_data = [
            {
                "agent_id": agent1_id,
                "interests": None,  # Invalid
            },
            {
                "agent_id": agent2_id,
                "interests": [["Technology"], [3]],  # Valid
            },
        ]

        # Batch initialize
        results = self.interest_manager.initialize_agent_interests_batch(agents_data, self.round_id)

        # Verify results
        self.assertFalse(results[agent1_id])  # Should fail
        self.assertTrue(results[agent2_id])  # Should succeed

        # Verify only valid agent is in memory
        agent_interests = self.interest_manager.get_agent_interests()
        self.assertNotIn(agent1_id, agent_interests)
        self.assertIn(agent2_id, agent_interests)

    def test_interest_service_batch_methods(self):
        """Test InterestService exposes batch methods correctly."""
        # Test add_or_get_interests_batch
        interest_names = ["Tech", "Science"]
        result = self.interest_service.add_or_get_interests_batch(interest_names)
        self.assertEqual(len(result), 2)

        # Test add_user_interests_batch
        user_id = str(uuid.uuid4())
        user_interests = [
            {
                "user_id": user_id,
                "interest_id": result["Tech"],
                "round_id": self.round_id,
            }
        ]
        added = self.interest_service.add_user_interests_batch(user_interests)
        self.assertEqual(added, 1)

        # Test add_agent_opinions_batch
        agent_id = str(uuid.uuid4())
        opinions = [
            {
                "agent_id": agent_id,
                "tid": self.round_id,
                "topic_id": result["Tech"],
                "opinion": 0.5,
                "id_interacted_with": None,
                "id_post": None,
            }
        ]
        added = self.interest_service.add_agent_opinions_batch(opinions)
        self.assertEqual(added, 1)


if __name__ == "__main__":
    unittest.main()
