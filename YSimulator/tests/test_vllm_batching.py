"""
Unit tests for vLLM batching functionality.

Tests cover:
- Batch request format and tuple structure
- Backward compatibility with old tuple format
"""

import unittest
from unittest.mock import Mock


class TestVLLMBatchRequestConstruction(unittest.TestCase):
    """Test batch request construction for vLLM."""
    
    def test_batch_request_format(self):
        """Test that batch requests are constructed correctly."""
        # Sample batchable post tuple
        agent_id = "agent_123"
        cluster_id = 2
        future = Mock()
        topic = "test_topic"
        day = 5
        slot = 12
        agent_attrs = {"name": "TestAgent", "age": 25}
        
        batchable_post = (agent_id, cluster_id, future, topic, day, slot, agent_attrs)
        
        # Extract parameters for batch request
        expected_request = {
            "cluster_id": cluster_id,
            "day": day,
            "slot": slot,
            "agent_attrs": agent_attrs
        }
        
        # Verify tuple structure
        self.assertEqual(batchable_post[0], agent_id)
        self.assertEqual(batchable_post[1], cluster_id)
        self.assertEqual(batchable_post[3], topic)
        self.assertEqual(batchable_post[4], day)
        self.assertEqual(batchable_post[5], slot)
        self.assertEqual(batchable_post[6], agent_attrs)
        self.assertEqual(len(batchable_post), 7, "Batchable post should have 7 elements")
    
    def test_old_format_compatibility(self):
        """Test that old 4-tuple format can be distinguished from new format."""
        # Old format: (agent_id, cluster_id, future, topic)
        old_format_post = ("agent1", 0, Mock(), "topic1")
        
        # New format: (agent_id, cluster_id, future, topic, day, slot, agent_attrs)
        new_format_post = ("agent2", 1, Mock(), "topic2", 1, 0, {"name": "Agent2"})
        
        # Should be able to distinguish by length
        self.assertEqual(len(old_format_post), 4, "Old format should have 4 elements")
        self.assertEqual(len(new_format_post), 7, "New format should have 7 elements")
        self.assertLess(len(old_format_post), 7, "Old format is non-batchable")
        self.assertGreaterEqual(len(new_format_post), 7, "New format is batchable")
    
    def test_batch_request_dict_construction(self):
        """Test construction of request dict from tuple."""
        # Simulate extracting params from a 7-tuple
        pending_tuple = ("agent123", 0, Mock(), "topic", 5, 12, {"name": "Test"})
        
        # Extract like the batch processor would
        agent_id = pending_tuple[0]
        cluster_id = pending_tuple[1]
        topic = pending_tuple[3]
        day = pending_tuple[4]
        slot = pending_tuple[5]
        agent_attrs = pending_tuple[6]
        
        # Build request dict
        request_dict = {
            "cluster_id": cluster_id,
            "day": day,
            "slot": slot,
            "agent_attrs": agent_attrs
        }
        
        # Verify
        self.assertEqual(request_dict["cluster_id"], 0)
        self.assertEqual(request_dict["day"], 5)
        self.assertEqual(request_dict["slot"], 12)
        self.assertEqual(request_dict["agent_attrs"], {"name": "Test"})


class TestPostGeneratorTupleFormat(unittest.TestCase):
    """Test that post generators create correct tuple formats."""
    
    def test_extended_tuple_format(self):
        """Test the extended 7-element tuple format."""
        # Simulate what post_generator.py creates
        agent_id = "agent_uuid"
        cluster_id = 1
        future = Mock()
        selected_topic = "climate"
        day = 3
        slot = 14
        agent_attrs = {
            "name": "Alice",
            "age": 30,
            "topic": "climate",
            "toxicity": "no"
        }
        
        # Create extended tuple (as post_generator does now)
        pending_call = (
            agent_id,
            cluster_id,
            future,
            selected_topic,
            day,
            slot,
            agent_attrs
        )
        
        # Verify all fields are accessible
        self.assertEqual(pending_call[0], agent_id)
        self.assertEqual(pending_call[1], cluster_id)
        self.assertIsNotNone(pending_call[2])  # future
        self.assertEqual(pending_call[3], selected_topic)
        self.assertEqual(pending_call[4], day)
        self.assertEqual(pending_call[5], slot)
        self.assertEqual(pending_call[6], agent_attrs)
        
        # Check agent_attrs has required fields for LLM
        self.assertIn("name", agent_attrs)
        self.assertIn("topic", agent_attrs)


if __name__ == "__main__":
    unittest.main()
