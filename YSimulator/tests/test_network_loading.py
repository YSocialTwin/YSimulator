"""
Unit tests for social network topology loading from network.csv.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import unittest
import uuid
import tempfile
import csv

from YSimulator.YServer.classes.models import Follow, User_mgmt, Round
from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware
from sqlalchemy.orm import Session


class TestNetworkLoading(unittest.TestCase):
    """Test social network topology loading from CSV."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create an in-memory SQLite database for testing
        self.db_config = {
            "type": "sqlite",
            "database": ":memory:"
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
        
        # Create test users
        self.user1_id = str(uuid.uuid4())
        self.user2_id = str(uuid.uuid4())
        self.user3_id = str(uuid.uuid4())
        
        with Session(self.db.engine) as session:
            user1 = User_mgmt(
                id=self.user1_id,
                username="test_user1",
                email="test1@example.com",
                leaning="neutral",
                user_type="agent"
            )
            user2 = User_mgmt(
                id=self.user2_id,
                username="test_user2",
                email="test2@example.com",
                leaning="neutral",
                user_type="agent"
            )
            user3 = User_mgmt(
                id=self.user3_id,
                username="test_user3",
                email="test3@example.com",
                leaning="neutral",
                user_type="agent"
            )
            session.add_all([user1, user2, user3])
            session.commit()
    
    def test_add_follow_sql(self):
        """Test adding a follow relationship to SQL database."""
        follow_data = {
            "user_id": self.user1_id,
            "follower_id": self.user2_id,
            "action": "follow",
            "round": ""
        }
        
        # Add follow relationship
        success = self.db.add_follow(follow_data)
        self.assertTrue(success)
        
        # Verify it was added
        with Session(self.db.engine) as session:
            follows = session.query(Follow).filter_by(
                user_id=self.user1_id,
                follower_id=self.user2_id
            ).all()
            self.assertEqual(len(follows), 1)
            self.assertEqual(follows[0].action, "follow")
    
    def test_add_multiple_follows(self):
        """Test adding multiple follow relationships."""
        # user2 follows user1
        follow1 = {
            "user_id": self.user1_id,
            "follower_id": self.user2_id,
            "action": "follow",
            "round": ""
        }
        # user3 follows user1
        follow2 = {
            "user_id": self.user1_id,
            "follower_id": self.user3_id,
            "action": "follow",
            "round": ""
        }
        # user2 follows user3
        follow3 = {
            "user_id": self.user3_id,
            "follower_id": self.user2_id,
            "action": "follow",
            "round": ""
        }
        
        # Add all follow relationships
        self.assertTrue(self.db.add_follow(follow1))
        self.assertTrue(self.db.add_follow(follow2))
        self.assertTrue(self.db.add_follow(follow3))
        
        # Verify count
        with Session(self.db.engine) as session:
            total_follows = session.query(Follow).count()
            self.assertEqual(total_follows, 3)
            
            # Verify user1 has 2 followers
            user1_followers = session.query(Follow).filter_by(
                user_id=self.user1_id,
                action="follow"
            ).count()
            self.assertEqual(user1_followers, 2)
    
    def test_csv_parsing_format(self):
        """Test that CSV parsing would work with expected format."""
        # Create a temporary CSV file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            writer = csv.writer(f)
            writer.writerow(['test_user2', 'test_user1'])  # user2 follows user1
            writer.writerow(['test_user3', 'test_user1'])  # user3 follows user1
            writer.writerow(['test_user2', 'test_user3'])  # user2 follows user3
            csv_path = f.name
        
        try:
            # Parse CSV and create follow relationships
            username_to_id = {
                'test_user1': self.user1_id,
                'test_user2': self.user2_id,
                'test_user3': self.user3_id,
            }
            
            follow_count = 0
            with open(csv_path, 'r') as csvfile:
                reader = csv.reader(csvfile)
                for row in reader:
                    if not row or len(row) < 2:
                        continue
                    
                    follower_name = row[0].strip()
                    user_name = row[1].strip()
                    
                    if follower_name in username_to_id and user_name in username_to_id:
                        follow_data = {
                            "follower_id": username_to_id[follower_name],
                            "user_id": username_to_id[user_name],
                            "action": "follow",
                            "round": "",
                        }
                        success = self.db.add_follow(follow_data)
                        if success:
                            follow_count += 1
            
            self.assertEqual(follow_count, 3)
            
            # Verify in database
            with Session(self.db.engine) as session:
                total_follows = session.query(Follow).count()
                self.assertEqual(total_follows, 3)
        
        finally:
            # Clean up temp file
            os.unlink(csv_path)


if __name__ == '__main__':
    unittest.main()
