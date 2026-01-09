"""
Unit tests for interest tracking implementation.
"""

from sqlalchemy.orm import Session
from YSimulator.YClient.classes.ray_models import ActionDTO, AgentProfile
from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware
from YSimulator.YServer.classes.models import (
    Interest,
    UserInterest,
    PostTopic,
    Post,
    User_mgmt,
    Round,
)
import uuid
import unittest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))


class TestInterestTracking(unittest.TestCase):
    """Test interest tracking functionality."""

    # Class-level counter to ensure unique day/hour combinations across all tests
    _round_counter = 1000  # Start at 1000 to avoid collision with other test classes

    def setUp(self):
        """Set up test fixtures."""
        # Create an in-memory SQLite database for testing
        self.db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}

        # Initialize database middleware
        self.db = DatabaseMiddleware(db_config=self.db_config, config_path=".", redis_config=None)

        # Create tables
        from YSimulator.YServer.classes.models import Base

        Base.metadata.create_all(self.db.engine)

        # Create test fixtures
        with Session(self.db.engine) as session:
            # Create round with unique day/hour to avoid UNIQUE constraint violations
            TestInterestTracking._round_counter += 1
            day = TestInterestTracking._round_counter // 24
            hour = TestInterestTracking._round_counter % 24
            self.round_id = str(uuid.uuid4())
            round_obj = Round(id=self.round_id, day=day, hour=hour)
            session.add(round_obj)

            # Create test user with unique username each time
            self.user_id = str(uuid.uuid4())
            user = User_mgmt(
                id=self.user_id,
                username=f"test_user_{self.user_id[:8]}",  # Make username unique
                email=f"test_{self.user_id[:8]}@example.com",  # Make email unique
                password="password",
                round_actions=3,
            )
            session.add(user)

            session.commit()

    def test_add_or_get_interest(self):
        """Test adding and retrieving interests."""
        # Add new interest
        interest_id = self.db.add_or_get_interest("Technology")
        self.assertIsNotNone(interest_id)

        # Get same interest again (should return existing ID)
        interest_id2 = self.db.add_or_get_interest("Technology")
        self.assertEqual(interest_id, interest_id2)

        # Verify interest exists in database
        with Session(self.db.engine) as session:
            interest = session.query(Interest).filter(Interest.iid == interest_id).first()
            self.assertIsNotNone(interest)
            self.assertEqual(interest.interest, "Technology")

    def test_add_user_interest(self):
        """Test adding user interest associations."""
        # Create an interest
        interest_id = self.db.add_or_get_interest("Sports")

        # Add user interest
        result = self.db.add_user_interest(self.user_id, interest_id, self.round_id)
        self.assertTrue(result)

        # Verify user interest exists
        with Session(self.db.engine) as session:
            user_interest = (
                session.query(UserInterest)
                .filter(
                    UserInterest.user_id == self.user_id, UserInterest.interest_id == interest_id
                )
                .first()
            )
            self.assertIsNotNone(user_interest)
            self.assertEqual(user_interest.round_id, self.round_id)

    def test_add_post_topic(self):
        """Test adding post topic associations."""
        # Create a post
        post_id = str(uuid.uuid4())
        post = Post(
            id=post_id,
            user_id=self.user_id,
            tweet="Test post about technology",
            round=self.round_id,
        )
        with Session(self.db.engine) as session:
            session.add(post)
            session.commit()

        # Create an interest
        topic_id = self.db.add_or_get_interest("Technology")

        # Add post topic
        result = self.db.add_post_topic(post_id, topic_id)
        self.assertTrue(result)

        # Verify post topic exists
        with Session(self.db.engine) as session:
            post_topic = (
                session.query(PostTopic)
                .filter(PostTopic.post_id == post_id, PostTopic.topic_id == topic_id)
                .first()
            )
            self.assertIsNotNone(post_topic)

    def test_get_post_topics(self):
        """Test retrieving topics for a post."""
        # Create a post
        post_id = str(uuid.uuid4())
        post = Post(
            id=post_id,
            user_id=self.user_id,
            tweet="Test post about multiple topics",
            round=self.round_id,
        )
        with Session(self.db.engine) as session:
            session.add(post)
            session.commit()

        # Add multiple topics
        topic_id1 = self.db.add_or_get_interest("Technology")
        topic_id2 = self.db.add_or_get_interest("Innovation")

        self.db.add_post_topic(post_id, topic_id1)
        self.db.add_post_topic(post_id, topic_id2)

        # Get post topics
        topics = self.db.get_post_topics(post_id)
        self.assertEqual(len(topics), 2)
        self.assertIn(topic_id1, topics)
        self.assertIn(topic_id2, topics)

    def test_agent_profile_with_interests(self):
        """Test AgentProfile with interests field."""
        # Create agent profile with interests
        agent = AgentProfile(
            id=str(uuid.uuid4()),
            username="tech_enthusiast",
            email="tech@example.com",
            interests=[["Technology", "AI", "Programming"], [5, 3, 2]],
        )

        # Verify interests field
        self.assertIsNotNone(agent.interests)
        self.assertEqual(len(agent.interests), 2)
        self.assertEqual(len(agent.interests[0]), 3)
        self.assertEqual(len(agent.interests[1]), 3)
        self.assertEqual(agent.interests[0][0], "Technology")
        self.assertEqual(agent.interests[1][0], 5)

    def test_action_dto_with_topic(self):
        """Test ActionDTO with topic field."""
        # Create action with topic
        action = ActionDTO(
            agent_id=self.user_id,
            cluster_id=0,
            action_type="POST",
            content="Discussing technology trends",
            topic="Technology",
        )

        # Verify topic field
        self.assertEqual(action.topic, "Technology")
        self.assertEqual(action.action_type, "POST")


if __name__ == "__main__":
    unittest.main()
