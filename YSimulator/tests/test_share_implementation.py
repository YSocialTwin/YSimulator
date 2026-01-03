"""
Unit tests for share action and thread_id implementation.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import unittest
import uuid

from YSimulator.YServer.classes.models import Website, Article, Post, User_mgmt, Round
from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware
from YSimulator.YClient.classes.ray_models import ActionDTO
from sqlalchemy.orm import Session


class TestShareImplementation(unittest.TestCase):
    """Test share action and thread_id implementation."""
    
    # Class-level counter to ensure unique day/hour combinations across all tests
    _round_counter = 3000  # Start at 3000 to avoid collision with other test classes
    
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
        
        # Create test fixtures - use unique day/hour for each test to avoid constraint errors
        with Session(self.db.engine) as session:
            # Create round with unique day/hour to avoid UNIQUE constraint violations
            TestShareImplementation._round_counter += 1
            day = TestShareImplementation._round_counter // 24
            hour = TestShareImplementation._round_counter % 24
            self.round_id = str(uuid.uuid4())
            round_obj = Round(id=self.round_id, day=day, hour=hour)
            session.add(round_obj)
            
            # Create user
            self.user_id = str(uuid.uuid4())
            user = User_mgmt(
                id=self.user_id,
                username=f"test_user_{uuid.uuid4().hex[:8]}",
                password="test_password"
            )
            session.add(user)
            session.commit()
    
    def test_01_post_creates_thread_id(self):
        """Test that a new post creates its own thread_id."""
        print("\n=== Test 1: Post Creates Thread ID ===")
        
        post_data = {
            "user_id": self.user_id,
            "tweet": "Test post",
            "round": self.round_id,
        }
        
        post_id = self.db.add_post(post_data)
        
        # Verify post was created
        self.assertIsNotNone(post_id)
        
        # Verify thread_id equals post_id
        post = self.db.get_post(post_id)
        self.assertEqual(post["thread_id"], post_id)
        print(f"✓ Post {post_id} has thread_id={post['thread_id']}")
    
    def test_02_comment_inherits_thread_id(self):
        """Test that a comment inherits the thread_id from its parent post."""
        print("\n=== Test 2: Comment Inherits Thread ID ===")
        
        # Create parent post
        parent_post_data = {
            "user_id": self.user_id,
            "tweet": "Parent post",
            "round": self.round_id,
        }
        parent_post_id = self.db.add_post(parent_post_data)
        parent_post = self.db.get_post(parent_post_id)
        
        print(f"Parent post: {parent_post_id}, thread_id={parent_post['thread_id']}")
        
        # Create comment with thread_id specified
        comment_data = {
            "user_id": self.user_id,
            "tweet": "Comment on post",
            "round": self.round_id,
            "comment_to": parent_post_id,
            "thread_id": parent_post["thread_id"],  # Inherit thread_id
        }
        comment_id = self.db.add_post(comment_data)
        
        # Verify comment has same thread_id as parent
        comment = self.db.get_post(comment_id)
        self.assertEqual(comment["thread_id"], parent_post["thread_id"])
        self.assertEqual(comment["comment_to"], parent_post_id)
        print(f"✓ Comment {comment_id} has thread_id={comment['thread_id']} (inherited from parent)")
    
    def test_03_share_creates_new_thread_id(self):
        """Test that a shared post creates its own thread_id."""
        print("\n=== Test 3: Share Creates New Thread ID ===")
        
        # Create original post
        original_post_data = {
            "user_id": self.user_id,
            "tweet": "Original post",
            "round": self.round_id,
        }
        original_post_id = self.db.add_post(original_post_data)
        original_post = self.db.get_post(original_post_id)
        
        print(f"Original post: {original_post_id}, thread_id={original_post['thread_id']}")
        
        # Create shared post
        share_data = {
            "user_id": self.user_id,
            "tweet": "Sharing this!",
            "round": self.round_id,
            "shared_from": original_post_id,
        }
        share_id = self.db.add_post(share_data)
        
        # Verify share has its own thread_id
        share = self.db.get_post(share_id)
        self.assertEqual(share["thread_id"], share_id)
        self.assertNotEqual(share["thread_id"], original_post["thread_id"])
        self.assertEqual(share["shared_from"], original_post_id)
        print(f"✓ Share {share_id} has thread_id={share['thread_id']} (new thread)")
    
    def test_04_share_with_news_id(self):
        """Test that sharing a news post copies the news_id."""
        print("\n=== Test 4: Share With News ID ===")
        
        # Create website and article
        website_data = {
            "name": "Test News",
            "rss": "https://test.com/feed.xml",
            "category": "tech",
            "language": "en"
        }
        website_id = self.db.add_website(website_data)
        
        article_data = {
            "title": "Test Article",
            "summary": "Test summary",
            "link": "https://test.com/article",
            "website_id": website_id
        }
        article_id = self.db.add_article(article_data)
        
        # Create news post
        news_post_data = {
            "user_id": self.user_id,
            "tweet": "Check out this news!",
            "round": self.round_id,
            "news_id": article_id,
        }
        news_post_id = self.db.add_post(news_post_data)
        news_post = self.db.get_post(news_post_id)
        
        print(f"News post: {news_post_id}, news_id={news_post['news_id']}")
        
        # Create shared post - should copy news_id
        share_data = {
            "user_id": self.user_id,
            "tweet": "Sharing this news!",
            "round": self.round_id,
            "shared_from": news_post_id,
            "news_id": news_post["news_id"],  # Copy news_id
        }
        share_id = self.db.add_post(share_data)
        
        # Verify share has same news_id
        share = self.db.get_post(share_id)
        self.assertEqual(share["news_id"], article_id)
        self.assertEqual(share["shared_from"], news_post_id)
        self.assertEqual(share["thread_id"], share_id)  # New thread
        print(f"✓ Share {share_id} has news_id={share['news_id']} (copied from original)")
    
    def test_05_action_dto_share(self):
        """Test that ActionDTO supports SHARE action type."""
        print("\n=== Test 5: ActionDTO Share Support ===")
        
        # Create a SHARE action
        action = ActionDTO(
            agent_id="agent-123",
            cluster_id=1,
            action_type="SHARE",
            content="Sharing this post!",
            target_post_id="post-uuid-123",
        )
        
        self.assertEqual(action.action_type, "SHARE")
        self.assertEqual(action.target_post_id, "post-uuid-123")
        print(f"✓ ActionDTO supports SHARE action type")
    
    def test_06_nested_comments_inherit_root_thread_id(self):
        """Test that nested comments (comment on a comment) inherit the root thread_id."""
        print("\n=== Test 6: Nested Comments Inherit Root Thread ID ===")
        
        # Create root post
        root_post_data = {
            "user_id": self.user_id,
            "tweet": "Root post",
            "round": self.round_id,
        }
        root_post_id = self.db.add_post(root_post_data)
        root_post = self.db.get_post(root_post_id)
        
        print(f"Root post: {root_post_id}, thread_id={root_post['thread_id']}")
        self.assertEqual(root_post["thread_id"], root_post_id, "Root post thread_id should equal post_id")
        
        # Create first-level comment on root post
        comment1_data = {
            "user_id": self.user_id,
            "tweet": "First level comment",
            "round": self.round_id,
            "comment_to": root_post_id,
            "thread_id": root_post["thread_id"],
        }
        comment1_id = self.db.add_post(comment1_data)
        comment1 = self.db.get_post(comment1_id)
        
        print(f"Comment 1: {comment1_id}, thread_id={comment1['thread_id']}, comment_to={comment1['comment_to']}")
        self.assertEqual(comment1["thread_id"], root_post_id, "First-level comment should have root thread_id")
        self.assertEqual(comment1["comment_to"], root_post_id, "First-level comment should reference root post")
        
        # Create second-level comment (comment on comment)
        comment2_data = {
            "user_id": self.user_id,
            "tweet": "Second level comment",
            "round": self.round_id,
            "comment_to": comment1_id,  # Commenting on the first comment
            "thread_id": comment1["thread_id"],  # Should inherit root thread_id from comment1
        }
        comment2_id = self.db.add_post(comment2_data)
        comment2 = self.db.get_post(comment2_id)
        
        print(f"Comment 2: {comment2_id}, thread_id={comment2['thread_id']}, comment_to={comment2['comment_to']}")
        self.assertEqual(comment2["thread_id"], root_post_id, "Second-level comment should have root thread_id")
        self.assertEqual(comment2["comment_to"], comment1_id, "Second-level comment should reference first comment")
        
        # Verify all posts in the thread have the same thread_id pointing to root
        self.assertEqual(root_post["thread_id"], root_post_id)
        self.assertEqual(comment1["thread_id"], root_post_id)
        self.assertEqual(comment2["thread_id"], root_post_id)
        
        print(f"✓ All comments in thread have thread_id={root_post_id} (root post ID)")
        print(f"  - Root post: {root_post_id}")
        print(f"  - Comment 1 (on root): {comment1_id} → {comment1['comment_to']}")
        print(f"  - Comment 2 (on comment 1): {comment2_id} → {comment2['comment_to']}")


def run_tests():
    """Run all tests and print results."""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestShareImplementation)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("✓ All tests passed!")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
