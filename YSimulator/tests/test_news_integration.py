"""
Unit tests for news feed database integration.

Tests the entire pipeline from news service to database writes.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import unittest
from unittest.mock import Mock, MagicMock, patch
import uuid
import json

# Import the modules we need to test
from YSimulator.YServer.classes.models import Website, Article, Post
from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware
from sqlalchemy.orm import Session


class TestNewsIntegration(unittest.TestCase):
    """Test news feed integration step by step."""
    
    # Class-level counter to ensure unique day/hour combinations across all tests
    _round_counter = 4000  # Start at 4000 to avoid collision with other test classes
    
    def setUp(self):
        """Set up test fixtures."""
        # Create an in-memory SQLite database for testing
        self.db_config = {
            "type": "sqlite",
            "sqlite": {
                "filename": ":memory:"
            }
        }
        
        # Initialize database middleware
        self.db = DatabaseMiddleware(
            db_config=self.db_config,
            config_path=".",
            redis_config=None
        )
        
        # Create tables
        from YSimulator.YServer.classes.models import Base
        Base.metadata.create_all(self.db.engine)
        
    def test_01_website_model_structure(self):
        """Test that Website model has correct structure."""
        print("\n=== Test 1: Website Model Structure ===")
        
        # Check Website model attributes
        self.assertTrue(hasattr(Website, 'id'))
        self.assertTrue(hasattr(Website, 'name'))
        self.assertTrue(hasattr(Website, 'rss'))
        self.assertTrue(hasattr(Website, 'category'))
        self.assertTrue(hasattr(Website, 'language'))
        
        # Check id column type
        id_col = Website.__table__.columns['id']
        print(f"Website.id type: {id_col.type}")
        print(f"Website.id type class: {id_col.type.__class__.__name__}")
        
        self.assertEqual(str(id_col.type), "VARCHAR(36)", 
                        "Website.id should be VARCHAR(36) for UUID")
        
        print("✓ Website model structure is correct")
    
    def test_02_article_model_structure(self):
        """Test that Article model has correct structure and FK."""
        print("\n=== Test 2: Article Model Structure ===")
        
        # Check Article model attributes
        self.assertTrue(hasattr(Article, 'id'))
        self.assertTrue(hasattr(Article, 'title'))
        self.assertTrue(hasattr(Article, 'summary'))
        self.assertTrue(hasattr(Article, 'link'))
        self.assertTrue(hasattr(Article, 'website_id'))
        
        # Check column types
        id_col = Article.__table__.columns['id']
        website_id_col = Article.__table__.columns['website_id']
        
        print(f"Article.id type: {id_col.type}")
        print(f"Article.website_id type: {website_id_col.type}")
        print(f"Article.website_id type class: {website_id_col.type.__class__.__name__}")
        
        # Verify FK type matches PK type
        self.assertEqual(str(website_id_col.type), "VARCHAR(36)",
                        "Article.website_id should be VARCHAR(36) to match Website.id")
        
        # Check foreign key constraint
        fk_constraints = [fk for fk in Article.__table__.foreign_keys]
        print(f"Article foreign keys: {fk_constraints}")
        self.assertEqual(len(fk_constraints), 1, "Article should have 1 foreign key")
        
        fk = list(fk_constraints)[0]
        print(f"FK column: {fk.parent}, references: {fk.column}")
        self.assertEqual(str(fk.column.table), "websites", 
                        "Article.website_id should reference websites table")
        
        print("✓ Article model structure is correct")
    
    def test_03_add_website_method(self):
        """Test adding a website to the database."""
        print("\n=== Test 3: Add Website Method ===")
        
        website_data = {
            "name": "Test News",
            "rss": "https://test.com/feed.xml",
            "category": "tech",
            "language": "en"
        }
        
        # Call add_website
        website_id = self.db.add_website(website_data)
        
        print(f"Created website ID: {website_id}")
        self.assertIsNotNone(website_id, "Website ID should not be None")
        self.assertIsInstance(website_id, str, "Website ID should be a string (UUID)")
        
        # Verify website is in database
        from sqlalchemy import select
        with Session(self.db.engine) as session:
            stmt = select(Website).where(Website.id == website_id)
            website = session.execute(stmt).scalar_one_or_none()
            
            self.assertIsNotNone(website, "Website should exist in database")
            self.assertEqual(website.name, "Test News")
            self.assertEqual(website.rss, "https://test.com/feed.xml")
            
            print(f"✓ Website saved: {website.name} (ID: {website.id})")
    
    def test_04_add_article_with_valid_website(self):
        """Test adding an article with a valid website reference."""
        print("\n=== Test 4: Add Article with Valid Website ===")
        
        # First create a website
        website_data = {
            "name": "Test News",
            "rss": "https://test.com/feed.xml",
            "category": "tech",
            "language": "en"
        }
        website_id = self.db.add_website(website_data)
        print(f"Created website ID: {website_id}")
        
        # Now create an article referencing this website
        article_data = {
            "title": "Test Article",
            "summary": "This is a test article summary.",
            "link": "https://test.com/article1",
            "website_id": website_id
        }
        
        # Call add_article
        article_id = self.db.add_article(article_data)
        
        print(f"Created article ID: {article_id}")
        self.assertIsNotNone(article_id, "Article ID should not be None")
        self.assertIsInstance(article_id, str, "Article ID should be a string (UUID)")
        
        # Verify article is in database
        from sqlalchemy import select
        with Session(self.db.engine) as session:
            stmt = select(Article).where(Article.id == article_id)
            article = session.execute(stmt).scalar_one_or_none()
            
            self.assertIsNotNone(article, "Article should exist in database")
            self.assertEqual(article.title, "Test Article")
            self.assertEqual(article.website_id, website_id)
            
            print(f"✓ Article saved: {article.title} (ID: {article.id})")
            print(f"✓ Article references website: {article.website_id}")
    
    def test_05_add_article_with_invalid_website(self):
        """Test that adding an article with invalid website_id fails gracefully."""
        print("\n=== Test 5: Add Article with Invalid Website ===")
        
        # Try to create article with non-existent website_id
        fake_website_id = str(uuid.uuid4())
        article_data = {
            "title": "Test Article",
            "summary": "This is a test article summary.",
            "link": "https://test.com/article1",
            "website_id": fake_website_id
        }
        
        # Call add_article - should return None
        article_id = self.db.add_article(article_data)
        
        print(f"Article ID with invalid website: {article_id}")
        self.assertIsNone(article_id, "Article with invalid website_id should return None")
        
        print("✓ Invalid website_id handled correctly")
    
    def test_06_get_website_by_rss(self):
        """Test retrieving website by RSS URL."""
        print("\n=== Test 6: Get Website by RSS ===")
        
        # Create a website
        website_data = {
            "name": "Test News",
            "rss": "https://test.com/feed.xml",
            "category": "tech",
            "language": "en"
        }
        website_id = self.db.add_website(website_data)
        
        # Retrieve by RSS URL
        retrieved = self.db.get_website_by_rss("https://test.com/feed.xml")
        
        self.assertIsNotNone(retrieved, "Website should be retrieved by RSS")
        self.assertEqual(retrieved["id"], website_id)
        self.assertEqual(retrieved["name"], "Test News")
        
        print(f"✓ Retrieved website by RSS: {retrieved['name']}")
    
    def test_07_duplicate_website_prevention(self):
        """Test that duplicate websites are not created."""
        print("\n=== Test 7: Duplicate Website Prevention ===")
        
        website_data = {
            "name": "Test News",
            "rss": "https://test.com/feed.xml",
            "category": "tech",
            "language": "en"
        }
        
        # Add website first time
        website_id_1 = self.db.add_website(website_data)
        
        # Try to add same website again
        website_id_2 = self.db.add_website(website_data)
        
        print(f"First add: {website_id_1}")
        print(f"Second add: {website_id_2}")
        
        self.assertEqual(website_id_1, website_id_2, 
                        "Adding same RSS URL should return existing website_id")
        
        # Verify only one website exists
        from sqlalchemy import select, func
        with Session(self.db.engine) as session:
            stmt = select(func.count()).select_from(Website).where(
                Website.rss == "https://test.com/feed.xml"
            )
            count = session.execute(stmt).scalar()
            
            self.assertEqual(count, 1, "Only one website should exist for this RSS URL")
        
        print("✓ Duplicate prevention working correctly")
    
    def test_08_full_news_flow(self):
        """Test the complete flow: Website → Article → Post."""
        print("\n=== Test 8: Full News Flow ===")
        
        # Step 1: Create website
        website_data = {
            "name": "Tech News",
            "rss": "https://technews.com/feed.xml",
            "category": "tech",
            "language": "en"
        }
        website_id = self.db.add_website(website_data)
        print(f"Step 1: Created website {website_id}")
        
        # Step 2: Create article
        article_data = {
            "title": "AI Breakthrough",
            "summary": "Scientists achieve major AI breakthrough...",
            "link": "https://technews.com/ai-breakthrough",
            "website_id": website_id
        }
        article_id = self.db.add_article(article_data)
        print(f"Step 2: Created article {article_id}")
        
        # Step 3: Create user for post
        from YSimulator.YServer.classes.models import User_mgmt, Round
        with Session(self.db.engine) as session:
            # Create round with unique day/hour to avoid UNIQUE constraint violations
            TestNewsIntegration._round_counter += 1
            day = TestNewsIntegration._round_counter // 24
            hour = TestNewsIntegration._round_counter % 24
            round_id = str(uuid.uuid4())
            round_obj = Round(id=round_id, day=day, hour=hour)
            session.add(round_obj)
            
            # Create user with unique username
            user_id = str(uuid.uuid4())
            user = User_mgmt(
                id=user_id,
                username=f"test_user_{user_id[:8]}",  # Make username unique
                password="test_password",  # Required field
                archetype="broadcaster",
                round_actions=3
            )
            session.add(user)
            session.commit()
            
            print(f"Step 3: Created user {user_id} and round {round_id}")
            
            # Step 4: Create post referencing article
            post_id = str(uuid.uuid4())
            post = Post(
                id=post_id,
                tweet="Check out this AI news!",  # Commentary
                user_id=user_id,
                round=round_id,
                news_id=article_id  # Link to article
            )
            session.add(post)
            session.commit()
            
            print(f"Step 4: Created post {post_id} with news_id={article_id}")
        
        # Step 5: Verify complete chain
        from sqlalchemy import select
        with Session(self.db.engine) as session:
            # Load post with relationships
            stmt = select(Post).where(Post.id == post_id)
            post = session.execute(stmt).scalar_one()
            
            print(f"\nPost details:")
            print(f"  ID: {post.id}")
            print(f"  Tweet: {post.tweet}")
            print(f"  User ID: {post.user_id}")
            print(f"  News ID: {post.news_id}")
            
            # Load referenced article
            stmt = select(Article).where(Article.id == post.news_id)
            article = session.execute(stmt).scalar_one()
            
            print(f"\nArticle details:")
            print(f"  ID: {article.id}")
            print(f"  Title: {article.title}")
            print(f"  Website ID: {article.website_id}")
            
            # Load referenced website
            stmt = select(Website).where(Website.id == article.website_id)
            website = session.execute(stmt).scalar_one()
            
            print(f"\nWebsite details:")
            print(f"  ID: {website.id}")
            print(f"  Name: {website.name}")
            print(f"  RSS: {website.rss}")
            
            # Verify chain
            self.assertEqual(post.news_id, article.id)
            self.assertEqual(article.website_id, website.id)
            
            print("\n✓ Complete chain verified: Post → Article → Website")


def run_tests():
    """Run all tests and print results."""
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestNewsIntegration)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.failures:
        print("\nFAILURES:")
        for test, traceback in result.failures:
            print(f"\n{test}:")
            print(traceback)
    
    if result.errors:
        print("\nERRORS:")
        for test, traceback in result.errors:
            print(f"\n{test}:")
            print(traceback)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
