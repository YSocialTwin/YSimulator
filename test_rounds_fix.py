#!/usr/bin/env python3
"""
Test script to verify the rounds table fix.

This tests that get_or_create_round can successfully create rounds
with UUID strings as IDs.
"""

import sys
import uuid
import tempfile
import os
from pathlib import Path

# Add the project to the path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from YSimulator.YServer.classes.models import Base, Round


def test_rounds_with_sqlite():
    """Test that rounds can be created with UUID strings in SQLite."""
    print("Testing rounds table with SQLite...")
    
    # Create an in-memory SQLite database
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    
    session = Session(engine)
    
    try:
        # Test creating a round with UUID string ID
        round_id = str(uuid.uuid4())
        day = 1
        hour = 1
        
        print(f"Creating round with ID={round_id}, day={day}, hour={hour}")
        round_obj = Round(id=round_id, day=day, hour=hour)
        session.add(round_obj)
        session.commit()
        
        # Verify it was created
        retrieved = session.query(Round).filter_by(day=day, hour=hour).first()
        assert retrieved is not None, "Round was not created"
        assert retrieved.id == round_id, f"Round ID mismatch: {retrieved.id} != {round_id}"
        assert retrieved.day == day, f"Day mismatch: {retrieved.day} != {day}"
        assert retrieved.hour == hour, f"Hour mismatch: {retrieved.hour} != {hour}"
        
        print("✓ Round created successfully with UUID string ID")
        
        # Test creating another round
        round_id2 = str(uuid.uuid4())
        round_obj2 = Round(id=round_id2, day=2, hour=2)
        session.add(round_obj2)
        session.commit()
        
        print("✓ Second round created successfully")
        
        # Test unique constraint
        try:
            duplicate = Round(id=str(uuid.uuid4()), day=1, hour=1)
            session.add(duplicate)
            session.commit()
            print("✗ Unique constraint not enforced!")
            return False
        except Exception as e:
            print(f"✓ Unique constraint working correctly: {e}")
            session.rollback()
        
        print("\n✓ All SQLite tests passed!")
        return True
        
    finally:
        session.close()


def test_get_or_create_round_method():
    """Test the get_or_create_round method from sql_repository."""
    print("\nTesting get_or_create_round method...")
    
    try:
        from YSimulator.YServer.repositories.sql_repository import SQLRecommendationRepository
        from sqlalchemy import create_engine
        import logging
        
        # Create a temporary database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            # Create engine and initialize tables
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(engine)
            
            logger = logging.getLogger(__name__)
            repo = SQLRecommendationRepository(engine, logger)
            
            # Test get_or_create_round
            round_id1 = repo.get_or_create_round(1, 1)
            print(f"Created round: {round_id1}")
            
            # Get it again - should return the same ID
            round_id2 = repo.get_or_create_round(1, 1)
            assert round_id1 == round_id2, f"Round IDs don't match: {round_id1} != {round_id2}"
            print(f"✓ get_or_create_round returns same ID for existing round")
            
            # Create a different round
            round_id3 = repo.get_or_create_round(2, 2)
            assert round_id3 != round_id1, "Different rounds should have different IDs"
            print(f"✓ Created different round: {round_id3}")
            
            print("\n✓ All get_or_create_round tests passed!")
            return True
            
        finally:
            # Clean up
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = True
    
    success = success and test_rounds_with_sqlite()
    success = success and test_get_or_create_round_method()
    
    if success:
        print("\n" + "="*50)
        print("ALL TESTS PASSED!")
        print("="*50)
        sys.exit(0)
    else:
        print("\n" + "="*50)
        print("SOME TESTS FAILED")
        print("="*50)
        sys.exit(1)
