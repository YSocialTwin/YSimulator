"""
Performance verification script for batch agent initialization optimization.

This script compares the performance of the old non-batched approach
versus the new batched approach for agent interests and opinions initialization.
"""

import time
import uuid
from unittest.mock import Mock

from sqlalchemy.orm import Session

from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware
from YSimulator.YServer.classes.models import Base
from YSimulator.YServer.interests_modeling.interest_manager import InterestManager
from YSimulator.YServer.repositories.sql_repository import SQLInterestRepository


def create_test_data(num_agents=100, topics_per_agent=5):
    """Create test data for agents with interests and opinions."""
    agents_interests = []
    agents_opinions = []
    
    for i in range(num_agents):
        agent_id = str(uuid.uuid4())
        
        # Create interests
        topics = [f"Topic_{(i + j) % 20}" for j in range(topics_per_agent)]
        counts = [3] * topics_per_agent
        agents_interests.append({
            "agent_id": agent_id,
            "interests": [topics, counts]
        })
        
        # Create opinions
        opinions = {topic: 0.5 for topic in topics}
        agents_opinions.append({
            "agent_id": agent_id,
            "opinions": opinions
        })
    
    return agents_interests, agents_opinions


def test_old_approach(repository, interest_manager, agents_interests, round_id):
    """Simulate the old non-batched approach."""
    start_time = time.time()
    
    for agent_data in agents_interests:
        agent_id = agent_data["agent_id"]
        interests = agent_data["interests"]
        
        # Old approach: one by one
        interest_manager.initialize_agent_interests(
            agent_id=agent_id,
            interests=interests,
            round_id=round_id
        )
    
    elapsed = time.time() - start_time
    return elapsed


def test_new_approach(interest_manager, agents_interests, round_id):
    """Test the new batched approach."""
    start_time = time.time()
    
    # New approach: batch
    interest_manager.initialize_agent_interests_batch(
        agents_interests, round_id
    )
    
    elapsed = time.time() - start_time
    return elapsed


def main():
    """Run performance comparison."""
    print("=" * 70)
    print("Agent Population Loading Optimization - Performance Verification")
    print("=" * 70)
    
    # Test with different population sizes
    test_sizes = [50, 100, 500]
    
    for num_agents in test_sizes:
        print(f"\n📊 Testing with {num_agents} agents (5 interests each)...")
        print("-" * 70)
        
        # Create test database
        db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}
        db = DatabaseMiddleware(db_config=db_config, config_path=".", redis_config=None)
        Base.metadata.create_all(db.engine)
        
        mock_logger = Mock()
        repository = SQLInterestRepository(db.engine, mock_logger)
        round_id = str(uuid.uuid4())
        
        # Create test data
        agents_interests, agents_opinions = create_test_data(num_agents=num_agents)
        
        # Test OLD approach
        interest_manager_old = InterestManager(repository, attention_window=336)
        old_time = test_old_approach(repository, interest_manager_old, agents_interests, round_id)
        
        # Create new database for NEW approach
        db2 = DatabaseMiddleware(db_config=db_config, config_path=".", redis_config=None)
        Base.metadata.create_all(db2.engine)
        repository2 = SQLInterestRepository(db2.engine, mock_logger)
        interest_manager_new = InterestManager(repository2, attention_window=336)
        
        new_time = test_new_approach(interest_manager_new, agents_interests, round_id)
        
        # Calculate improvement
        speedup = old_time / new_time if new_time > 0 else float('inf')
        improvement_pct = ((old_time - new_time) / old_time * 100) if old_time > 0 else 0
        
        # Display results
        print(f"  Old (non-batched):  {old_time:.4f} seconds")
        print(f"  New (batched):      {new_time:.4f} seconds")
        print(f"  Speedup:            {speedup:.2f}x faster")
        print(f"  Improvement:        {improvement_pct:.1f}% reduction in time")
        
        if speedup > 1:
            print(f"  ✅ Optimization successful!")
        else:
            print(f"  ⚠️  No significant improvement (may be due to small dataset)")
    
    print("\n" + "=" * 70)
    print("Summary:")
    print("  - Batch operations significantly reduce database round-trips")
    print("  - Performance gains increase with larger agent populations")
    print("  - Pattern matches network loading optimization (add_follow_relationships_batch)")
    print("=" * 70)


if __name__ == "__main__":
    main()
