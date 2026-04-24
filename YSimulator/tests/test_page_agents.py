"""
Unit tests for page agent integration.
"""

import sys
import unittest
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from YSimulator.YClient.classes.ray_models import AgentProfile
from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware
from YSimulator.YServer.classes.models import Article, Post, Round, User_mgmt, Website
from YSimulator.YServer.repositories.sql_repository import SQLArticleRepository

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))


class TestPageAgentIntegration(unittest.TestCase):
    """Test page agent integration."""

    # Class-level counter to ensure unique day/hour combinations across all tests
    _round_counter = 5000  # Start at 5000 to avoid collision with other test classes

    def setUp(self):
        """Set up test fixtures."""
        # Create an in-memory SQLite database for testing
        self.db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}

        # Initialize database middleware
        self.db = DatabaseMiddleware(db_config=self.db_config, config_path=".", redis_config=None)

        # Create tables
        from YSimulator.YServer.classes.models import Base

        Base.metadata.create_all(self.db.engine)

        # Create test fixtures - use unique day/hour for each test
        with Session(self.db.engine) as session:
            # Create round with unique day/hour to avoid UNIQUE constraint violations
            TestPageAgentIntegration._round_counter += 1
            day = TestPageAgentIntegration._round_counter // 24
            hour = TestPageAgentIntegration._round_counter % 24
            self.round_id = str(uuid.uuid4())
            round_obj = Round(id=self.round_id, day=day, hour=hour)
            session.add(round_obj)
            session.commit()

    def test_01_agent_profile_has_feed_url(self):
        """Test that AgentProfile supports feed_url field."""
        print("\n=== Test 1: AgentProfile Feed URL Support ===")

        # Create a page agent profile
        page_profile = AgentProfile(
            id="page-001", username="test_page", is_page=1, feed_url="https://example.com/feed.xml"
        )

        self.assertEqual(page_profile.is_page, 1)
        self.assertEqual(page_profile.feed_url, "https://example.com/feed.xml")
        print("✓ AgentProfile supports is_page and feed_url fields")

    def test_02_page_agent_creates_website(self):
        """Test that page agent registration creates a Website entry."""
        print("\n=== Test 2: Page Agent Creates Website ===")

        page_id = str(uuid.uuid4())
        feed_url = f"https://example.com/{uuid.uuid4().hex[:8]}/feed.xml"
        username = f"test_page_{uuid.uuid4().hex[:8]}"

        # Create user (page agent)
        user_data = {
            "id": page_id,
            "username": username,
            "password": "test123",
            "is_page": 1,
            "language": "en",
            "nationality": "US",
            "leaning": "neutral",
        }

        # Register user
        self.db.register_user(user_data)

        # Create website with same ID
        website_data = {
            "id": page_id,  # Website ID = Page ID
            "name": username,
            "rss": feed_url,
            "category": "page",
            "language": "en",
            "country": "US",
            "leaning": "neutral",
        }

        website_id = self.db.add_website(website_data)

        self.assertIsNotNone(website_id)
        self.assertEqual(website_id, page_id)

        # Verify website exists
        with Session(self.db.engine) as session:
            from sqlalchemy import select

            stmt = select(Website).where(Website.id == page_id)
            website = session.execute(stmt).scalar_one_or_none()

            self.assertIsNotNone(website)
            self.assertEqual(website.id, page_id)
            self.assertEqual(website.rss, feed_url)
            self.assertEqual(website.category, "page")

            print(f"✓ Website created with id={page_id} (same as user)")
            print(f"  RSS: {website.rss}")
            print(f"  Category: {website.category}")

    def test_03_regular_agent_no_website(self):
        """Test that regular agents don't create Website entries."""
        print("\n=== Test 3: Regular Agent No Website ===")

        regular_id = str(uuid.uuid4())
        username = f"regular_agent_{uuid.uuid4().hex[:8]}"

        # Create regular user (not a page)
        user_data = {"id": regular_id, "username": username, "password": "test123", "is_page": 0}

        # Register user
        result = self.db.register_user(user_data)
        self.assertTrue(result, "User registration should succeed")

        # Verify user exists but no website
        with Session(self.db.engine) as session:
            from sqlalchemy import select

            stmt = select(User_mgmt).where(User_mgmt.id == regular_id)
            user = session.execute(stmt).scalar_one_or_none()
            self.assertIsNotNone(user)
            self.assertEqual(user.is_page, 0)

            stmt = select(Website).where(Website.id == regular_id)
            website = session.execute(stmt).scalar_one_or_none()
            self.assertIsNone(website)

            print("✓ Regular agent exists without Website entry")

    def test_04_multiple_pages_different_feeds(self):
        """Test multiple page agents with different feeds."""
        print("\n=== Test 4: Multiple Pages with Different Feeds ===")

        pages = [
            {
                "id": str(uuid.uuid4()),
                "username": "tech_page",
                "feed": "https://tech.example.com/feed.xml",
            },
            {
                "id": str(uuid.uuid4()),
                "username": "news_page",
                "feed": "https://news.example.com/feed.xml",
            },
            {
                "id": str(uuid.uuid4()),
                "username": "sports_page",
                "feed": "https://sports.example.com/feed.xml",
            },
        ]

        created_ids = []
        for page in pages:
            # Register user
            user_data = {
                "id": page["id"],
                "username": page["username"],
                "password": "test123",
                "is_page": 1,
            }
            self.db.register_user(user_data)

            # Create website
            website_data = {
                "id": page["id"],
                "name": page["username"],
                "rss": page["feed"],
                "category": "page",
            }
            website_id = self.db.add_website(website_data)
            print(f"  Created website: expected_id={page['id']}, returned_id={website_id}")
            self.assertEqual(website_id, page["id"], f"Website ID mismatch for {page['username']}")
            created_ids.append(page["id"])

        # Verify all pages have websites
        with Session(self.db.engine) as session:
            from sqlalchemy import select

            # Count only the websites we created in this test
            for page_id in created_ids:
                stmt = select(Website).where(Website.id == page_id)
                website = session.execute(stmt).scalar_one_or_none()
                self.assertIsNotNone(website)

            print(f"✓ Created {len(created_ids)} page agents with unique feeds")

            # Verify each has correct feed
            for page in pages:
                stmt = select(Website).where(Website.id == page["id"])
                website = session.execute(stmt).scalar_one()
                self.assertEqual(website.rss, page["feed"])
                print(f"  {website.name}: {website.rss}")

    def test_05_page_article_reuse_respects_24_slot_cooldown(self):
        """Page article selection should prefer new feed items and only reuse old ones after cooldown."""
        page_id = str(uuid.uuid4())
        website_id = page_id

        with Session(self.db.engine) as session:
            session.add(
                User_mgmt(
                    id=page_id,
                    username="cooldown_page",
                    password="test123",
                    is_page=1,
                )
            )
            session.add(
                Website(
                    id=website_id,
                    name="cooldown_page",
                    rss="https://example.com/cooldown.xml",
                    category="page",
                )
            )

            old_round = Round(id=str(uuid.uuid4()), day=0, hour=0)
            recent_round = Round(id=str(uuid.uuid4()), day=1, hour=18)
            current_round = Round(id=str(uuid.uuid4()), day=2, hour=0)
            old_round_id = old_round.id
            recent_round_id = recent_round.id
            current_round_id = current_round.id
            session.add_all([old_round, recent_round, current_round])

            old_article = Article(
                id=str(uuid.uuid4()),
                title="Old Article",
                summary="Old summary",
                website_id=website_id,
                fetched_on=str(uuid.uuid4()),
                link="https://example.com/old",
            )
            recent_article = Article(
                id=str(uuid.uuid4()),
                title="Recent Article",
                summary="Recent summary",
                website_id=website_id,
                fetched_on=str(uuid.uuid4()),
                link="https://example.com/recent",
            )
            session.add_all([old_article, recent_article])

            session.add_all(
                [
                    Post(
                        id=str(uuid.uuid4()),
                        tweet="old share",
                        user_id=page_id,
                        comment_to="-1",
                        thread_id=str(uuid.uuid4()),
                        round=old_round_id,
                        news_id=old_article.id,
                        shared_from="-1",
                    ),
                    Post(
                        id=str(uuid.uuid4()),
                        tweet="recent share",
                        user_id=page_id,
                        comment_to="-1",
                        thread_id=str(uuid.uuid4()),
                        round=recent_round_id,
                        news_id=recent_article.id,
                        shared_from="-1",
                    ),
                ]
            )
            session.commit()

        repo = SQLArticleRepository(self.db.engine)

        selected = repo.select_page_article_for_sharing(
            website_id=website_id,
            current_round_id=current_round_id,
            feed_articles=[
                {"title": "Recent feed copy", "link": "https://example.com/recent"},
            ],
            cooldown_slots=24,
        )
        self.assertEqual(selected["link"], "https://example.com/old")

        selected_new = repo.select_page_article_for_sharing(
            website_id=website_id,
            current_round_id=current_round_id,
            feed_articles=[
                {"title": "Brand New", "link": "https://example.com/new"},
                {"title": "Recent feed copy", "link": "https://example.com/recent"},
            ],
            cooldown_slots=24,
        )
        self.assertEqual(selected_new["link"], "https://example.com/new")


def run_tests():
    """Run all tests and print results."""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPageAgentIntegration)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.wasSuccessful():
        print("✓ All tests passed!")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
