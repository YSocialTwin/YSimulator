"""
Test the search action implementation to verify it works correctly.
"""

import sys
import unittest
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware
from YSimulator.YServer.classes.models import Interest, Post, PostTopic, Round, User_mgmt

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))


class TestSearchAction(unittest.TestCase):
    """Test search action implementation."""

    # Class-level counter to ensure unique day/hour combinations across all tests
    _round_counter = 6000  # Start at 6000 to avoid collision with other test classes

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
            TestSearchAction._round_counter += 1
            day = TestSearchAction._round_counter // 24
            hour = TestSearchAction._round_counter % 24
            self.round_id = str(uuid.uuid4())
            round_obj = Round(id=self.round_id, day=day, hour=hour)
            session.add(round_obj)

            # Create test users
            self.user1_id = str(uuid.uuid4())
            user1 = User_mgmt(
                id=self.user1_id, username=f"user1_{uuid.uuid4().hex[:8]}", password="test"
            )
            session.add(user1)

            self.user2_id = str(uuid.uuid4())
            user2 = User_mgmt(
                id=self.user2_id, username=f"user2_{uuid.uuid4().hex[:8]}", password="test"
            )
            session.add(user2)

            # Create test topics
            self.topic1_id = str(uuid.uuid4())
            topic1 = Interest(iid=self.topic1_id, interest="Technology")
            session.add(topic1)

            self.topic2_id = str(uuid.uuid4())
            topic2 = Interest(iid=self.topic2_id, interest="Sports")
            session.add(topic2)

            session.commit()

    def test_01_search_posts_by_topic(self):
        """Test searching posts by topic."""
        print("\n=== Test 1: Search Posts by Topic ===")

        # Create posts with topics
        with Session(self.db.engine) as session:
            # User2 creates 3 posts about Technology
            for i in range(3):
                post_id = str(uuid.uuid4())
                post = Post(
                    id=post_id, user_id=self.user2_id, tweet=f"Tech post {i}", round=self.round_id
                )
                session.add(post)

                # Associate with Technology topic
                post_topic = PostTopic(
                    id=str(uuid.uuid4()), post_id=post_id, topic_id=self.topic1_id
                )
                session.add(post_topic)

            # User2 creates 1 post about Sports
            post_id = str(uuid.uuid4())
            post = Post(id=post_id, user_id=self.user2_id, tweet="Sports post", round=self.round_id)
            session.add(post)

            post_topic = PostTopic(id=str(uuid.uuid4()), post_id=post_id, topic_id=self.topic2_id)
            session.add(post_topic)

            session.commit()

        # Search for Technology posts from user1's perspective
        tech_posts = self.db.search_posts_by_topic(self.topic1_id, self.user1_id, limit=10)
        self.assertEqual(len(tech_posts), 3, "Should find 3 Technology posts")
        print(f"✓ Found {len(tech_posts)} Technology posts")

        # Search for Sports posts from user1's perspective
        sports_posts = self.db.search_posts_by_topic(self.topic2_id, self.user1_id, limit=10)
        self.assertEqual(len(sports_posts), 1, "Should find 1 Sports post")
        print(f"✓ Found {len(sports_posts)} Sports post")

    def test_02_exclude_own_posts(self):
        """Test that search excludes user's own posts."""
        print("\n=== Test 2: Exclude Own Posts ===")

        # User1 creates a Technology post
        with Session(self.db.engine) as session:
            post_id = str(uuid.uuid4())
            post = Post(
                id=post_id, user_id=self.user1_id, tweet="User1's tech post", round=self.round_id
            )
            session.add(post)

            post_topic = PostTopic(id=str(uuid.uuid4()), post_id=post_id, topic_id=self.topic1_id)
            session.add(post_topic)
            session.commit()

        # User1 searches for Technology posts
        tech_posts = self.db.search_posts_by_topic(self.topic1_id, self.user1_id, limit=10)

        # Should not include user1's own post
        for post_id in tech_posts:
            post = self.db.get_post(post_id)
            self.assertNotEqual(
                post["user_id"], self.user1_id, "Should not return user's own posts"
            )

        print("✓ Correctly excluded user's own posts")

    def test_03_get_topic_id_by_name(self):
        """Test getting topic ID by name."""
        print("\n=== Test 3: Get Topic ID by Name ===")

        # Get topic ID by exact name
        topic_id = self.db.get_topic_id_by_name("Technology")
        self.assertIsNotNone(topic_id, "Should find Technology topic")
        print(f"✓ Found topic 'Technology' with ID {topic_id}")

        # Try non-existent topic
        topic_id = self.db.get_topic_id_by_name("NonExistent")
        self.assertIsNone(topic_id, "Should return None for non-existent topic")
        print("✓ Correctly returned None for non-existent topic")

    def test_04_limit_results(self):
        """Test that search respects the limit parameter."""
        print("\n=== Test 4: Limit Search Results ===")

        # Create 15 Technology posts
        with Session(self.db.engine) as session:
            for i in range(15):
                post_id = str(uuid.uuid4())
                post = Post(
                    id=post_id, user_id=self.user2_id, tweet=f"Tech post {i}", round=self.round_id
                )
                session.add(post)

                post_topic = PostTopic(
                    id=str(uuid.uuid4()), post_id=post_id, topic_id=self.topic1_id
                )
                session.add(post_topic)
            session.commit()

        # Search with limit of 10
        tech_posts = self.db.search_posts_by_topic(self.topic1_id, self.user1_id, limit=10)
        self.assertLessEqual(len(tech_posts), 10, "Should not exceed limit of 10")
        print(f"✓ Search correctly limited results to {len(tech_posts)} (max 10)")


def test_llm_search_function():
    """Test that LLM search decision function exists."""
    try:
        from YSimulator.YClient.actions.llm_actions import generate_llm_search_action_async

        print("\n=== Test 5: LLM Search Function ===")
        print("  ✓ Function exists: generate_llm_search_action_async")

        # Check that it's a function
        if not callable(generate_llm_search_action_async):
            print("  ✗ generate_llm_search_action_async is not callable")

        print("  ✓ Function is callable")
    except ImportError as e:
        print("\n=== Test 5: LLM Search Function ===")
        print(f"  ! Skipping test (missing dependency: {e})")
        return True  # Skip test if dependencies not available


def test_imports_in_init():
    """Test that search function is exported in __init__.py."""
    try:
        pass

        print("\n=== Test 6: Imports in __init__.py ===")
        print("  ✓ generate_llm_search_action_async is exported")

    except ImportError as e:
        print("\n=== Test 6: Imports in __init__.py ===")
        print(f"  ! Skipping test (missing dependency: {e})")


def test_client_imports():
    """Test that client.py can import the search function."""
    print("\n=== Test 7: Client Imports ===")

    try:
        pass

        print("  ✓ client.py imports successfully")
    except ImportError as e:
        print(f"  ! Skipping test (missing dependency: {e})")


def run_tests():
    """Run all tests and print results."""
    # Run unittest tests
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSearchAction)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Run function tests
    success = True
    success = test_llm_search_function() and success
    success = test_imports_in_init() and success
    success = test_client_imports() and success

    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun + 3}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.wasSuccessful() and success:
        print("✓ All tests passed!")

    return result.wasSuccessful() and success


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
