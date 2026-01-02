"""
Unit tests for thread context retrieval implementation.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import unittest
import uuid

from YSimulator.YServer.classes.models import Post, User_mgmt, Round
from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware
from sqlalchemy.orm import Session


class TestThreadContext(unittest.TestCase):
    """Test thread context retrieval for comment action."""
    
    # Class-level counter to ensure unique day/hour combinations across all tests
    _round_counter = 2000  # Start at 2000 to avoid collision with other test classes
    
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
        
        # Create test fixtures with unique values for each test
        with Session(self.db.engine) as session:
            # Create rounds with unique day/hour combinations to avoid UNIQUE constraint violations
            unique_id = uuid.uuid4().hex[:8]
            TestThreadContext._round_counter += 1
            base_day = TestThreadContext._round_counter * 10  # Use counter-based day to ensure uniqueness
            
            self.round1_id = str(uuid.uuid4())
            self.round2_id = str(uuid.uuid4())
            self.round3_id = str(uuid.uuid4())
            self.round4_id = str(uuid.uuid4())
            
            round1 = Round(id=self.round1_id, day=base_day, hour=0)
            round2 = Round(id=self.round2_id, day=base_day, hour=1)
            round3 = Round(id=self.round3_id, day=base_day, hour=2)
            round4 = Round(id=self.round4_id, day=base_day, hour=3)
            session.add_all([round1, round2, round3, round4])
            
            # Create users with unique usernames
            self.user1_id = str(uuid.uuid4())
            self.user2_id = str(uuid.uuid4())
            self.user3_id = str(uuid.uuid4())
            
            user1 = User_mgmt(
                id=self.user1_id,
                username=f"alice_{unique_id}",
                password="test_password"
            )
            user2 = User_mgmt(
                id=self.user2_id,
                username=f"bob_{unique_id}",
                password="test_password"
            )
            user3 = User_mgmt(
                id=self.user3_id,
                username=f"charlie_{unique_id}",
                password="test_password"
            )
            session.add_all([user1, user2, user3])
            session.commit()
            
            # Store usernames for test assertions
            self.user1_name = f"alice_{unique_id}"
            self.user2_name = f"bob_{unique_id}"
            self.user3_name = f"charlie_{unique_id}"
    
    def test_01_empty_thread_context(self):
        """Test that a root post with no comments returns empty context."""
        print("\n=== Test 1: Empty Thread Context ===")
        
        # Create a root post
        post_data = {
            "user_id": self.user1_id,
            "tweet": "Root post",
            "round": self.round1_id,
        }
        post_id = self.db.add_post(post_data)
        
        # Get thread context (should be empty)
        context = self.db.get_thread_context(post_id, max_length=5)
        
        self.assertEqual(len(context), 0)
        print("✓ Root post has empty thread context")
    
    def test_02_single_comment_thread_context(self):
        """Test thread context for a comment on a root post."""
        print("\n=== Test 2: Single Comment Thread Context ===")
        
        # Create root post
        root_post_data = {
            "user_id": self.user1_id,
            "tweet": "Root post",
            "round": self.round1_id,
        }
        root_post_id = self.db.add_post(root_post_data)
        root_post = self.db.get_post(root_post_id)
        
        # Create comment
        comment_data = {
            "user_id": self.user2_id,
            "tweet": "First comment",
            "round": self.round2_id,
            "comment_to": root_post_id,
            "thread_id": root_post["thread_id"],
        }
        comment_id = self.db.add_post(comment_data)
        
        # Get thread context for the comment
        context = self.db.get_thread_context(comment_id, max_length=5)
        
        # Should return the root post
        self.assertEqual(len(context), 1)
        self.assertEqual(context[0]["username"], self.user1_name)
        self.assertEqual(context[0]["tweet"], "Root post")
        print(f"✓ Comment has 1 item in context: {context[0]['username']}: {context[0]['tweet']}")
    
    def test_03_multiple_comments_thread_context(self):
        """Test thread context with multiple comments in chronological order."""
        print("\n=== Test 3: Multiple Comments Thread Context ===")
        
        # Create root post
        root_post_data = {
            "user_id": self.user1_id,
            "tweet": "Root post",
            "round": self.round1_id,
        }
        root_post_id = self.db.add_post(root_post_data)
        root_post = self.db.get_post(root_post_id)
        
        # Create first comment
        comment1_data = {
            "user_id": self.user2_id,
            "tweet": "First comment by Bob",
            "round": self.round2_id,
            "comment_to": root_post_id,
            "thread_id": root_post["thread_id"],
        }
        comment1_id = self.db.add_post(comment1_data)
        
        # Create second comment
        comment2_data = {
            "user_id": self.user3_id,
            "tweet": "Second comment by Charlie",
            "round": self.round3_id,
            "comment_to": root_post_id,
            "thread_id": root_post["thread_id"],
        }
        comment2_id = self.db.add_post(comment2_data)
        
        # Create third comment (the one we're getting context for)
        comment3_data = {
            "user_id": self.user1_id,
            "tweet": "Third comment by Alice",
            "round": self.round4_id,
            "comment_to": root_post_id,
            "thread_id": root_post["thread_id"],
        }
        comment3_id = self.db.add_post(comment3_data)
        
        # Get thread context for the third comment
        context = self.db.get_thread_context(comment3_id, max_length=5)
        
        # Should return root post and 2 comments in chronological order
        self.assertEqual(len(context), 3)
        self.assertEqual(context[0]["username"], self.user1_name)
        self.assertEqual(context[0]["tweet"], "Root post")
        self.assertEqual(context[1]["username"], self.user2_name)
        self.assertEqual(context[1]["tweet"], "First comment by Bob")
        self.assertEqual(context[2]["username"], self.user3_name)
        self.assertEqual(context[2]["tweet"], "Second comment by Charlie")
        
        print("✓ Thread context returned in chronological order:")
        for i, ctx in enumerate(context):
            print(f"  {i+1}. {ctx['username']}: {ctx['tweet']}")
    
    def test_04_max_length_limit(self):
        """Test that thread context respects max_length limit."""
        print("\n=== Test 4: Max Length Limit ===")
        
        # Create root post
        root_post_data = {
            "user_id": self.user1_id,
            "tweet": "Root post",
            "round": self.round1_id,
        }
        root_post_id = self.db.add_post(root_post_data)
        root_post = self.db.get_post(root_post_id)
        
        # Create multiple comments
        comment_ids = []
        import random
        base_day = random.randint(1000, 10000)  # Use high number to avoid conflicts
        
        # Create all rounds first
        round_ids = []
        with Session(self.db.engine) as session:
            for i in range(10):
                round_id = str(uuid.uuid4())
                round_obj = Round(id=round_id, day=base_day + i, hour=0)
                session.add(round_obj)
                round_ids.append(round_id)
            session.commit()
        
        # Create comments using the rounds
        for i in range(10):
            comment_data = {
                "user_id": self.user2_id,
                "tweet": f"Comment {i+1}",
                "round": round_ids[i],
                "comment_to": root_post_id,
                "thread_id": root_post["thread_id"],
            }
            comment_id = self.db.add_post(comment_data)
            comment_ids.append(comment_id)
        
        # Get thread context for the last comment with max_length=5
        context = self.db.get_thread_context(comment_ids[-1], max_length=5)
        
        # Should return only 5 most recent items (root post + comments 5-9)
        self.assertEqual(len(context), 5)
        # First item should be comment 5, not root post
        self.assertIn("Comment", context[0]["tweet"])
        
        print(f"✓ Thread context limited to {len(context)} items (max_length=5)")
        for ctx in context:
            print(f"  - {ctx['username']}: {ctx['tweet']}")
    
    def test_05_nested_comments(self):
        """Test thread context with nested comments (comment on comment)."""
        print("\n=== Test 5: Nested Comments ===")
        
        # Create root post
        root_post_data = {
            "user_id": self.user1_id,
            "tweet": "Root post by Alice",
            "round": self.round1_id,
        }
        root_post_id = self.db.add_post(root_post_data)
        root_post = self.db.get_post(root_post_id)
        
        # Create first-level comment
        comment1_data = {
            "user_id": self.user2_id,
            "tweet": "First level comment by Bob",
            "round": self.round2_id,
            "comment_to": root_post_id,
            "thread_id": root_post["thread_id"],
        }
        comment1_id = self.db.add_post(comment1_data)
        
        # Create second-level comment (comment on comment)
        comment2_data = {
            "user_id": self.user3_id,
            "tweet": "Second level comment by Charlie",
            "round": self.round3_id,
            "comment_to": comment1_id,
            "thread_id": root_post["thread_id"],
        }
        comment2_id = self.db.add_post(comment2_data)
        
        # Get thread context for the nested comment
        context = self.db.get_thread_context(comment2_id, max_length=5)
        
        # Should return root post and first comment
        self.assertEqual(len(context), 2)
        self.assertEqual(context[0]["username"], self.user1_name)
        self.assertEqual(context[0]["tweet"], "Root post by Alice")
        self.assertEqual(context[1]["username"], self.user2_name)
        self.assertEqual(context[1]["tweet"], "First level comment by Bob")
        
        print("✓ Nested comment has correct thread context:")
        for ctx in context:
            print(f"  - {ctx['username']}: {ctx['tweet']}")


if __name__ == "__main__":
    unittest.main()
