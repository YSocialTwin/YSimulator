#!/usr/bin/env python3
"""
Integration test for action logging methods.

This script tests the actual logging methods added to the SimulationClient class.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock
import logging

# Mock ray to avoid dependency issues
sys.modules['ray'] = Mock()

# Import after mocking ray
from YSimulator.YClient.client import SimulationClient


def test_logging_methods():
    """Test the logging methods work correctly."""
    # Create a temporary directory for logs
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Mock configuration
        simulation_config = {
            "simulation": {
                "num_days": 1,
                "num_slots_per_day": 24,
                "heartbeat_interval": 5,
                "activity_profiles": {},
                "hourly_activity": {},
                "actions_likelihood": {},
                "enable_sentiment": False,
                "enable_toxicity": False,
                "enable_emotions": False,
                "emotion_annotation": False
            },
            "agents": {
                "probability_of_secondary_follow": 0.0,
                "probability_of_daily_follow": 0.0,
                "max_length_thread_reading": 5,
                "attention_window": 336
            },
            "posts": {
                "visibility_rounds": 36
            }
        }
        
        # Mock objects
        mock_llm = Mock()
        mock_server = Mock()
        
        # Patch ray.get_actor to return mock server
        import ray
        ray.get_actor = Mock(return_value=mock_server)
        
        # Create client instance
        try:
            client = SimulationClient(
                client_id="test_client",
                llm_handle=mock_llm,
                agent_config={"agents": []},
                simulation_config=simulation_config,
                config_path=str(temp_path),
                parent_logger=None,
                news_service_handle=None
            )
            
            # Test action logging
            client._log_action("TestAgent", "post", 0.0086, True, 0, 10)
            
            # Test hourly summary
            client._log_hourly_summary(0, 10)
            
            # Add more actions for daily summary
            client._log_action("TestAgent", "comment", 0.0042, True, 0, 23)
            client._log_action("TestAgent2", "read", 0.0035, True, 0, 23)
            
            # Test daily summary
            client._log_daily_summary(0)
            
            # Read the log file and verify entries
            log_file = temp_path / "logs" / "test_client_actions.log"
            assert log_file.exists(), f"Log file not created at {log_file}"
            
            with open(log_file, 'r') as f:
                lines = f.readlines()
            
            assert len(lines) >= 4, f"Expected at least 4 log entries, got {len(lines)}"
            
            # Parse and verify first action log
            first_entry = json.loads(lines[0])
            assert "time" in first_entry, "Missing 'time' field"
            assert first_entry["agent_name"] == "TestAgent", "Wrong agent_name"
            assert first_entry["method_name"] == "post", "Wrong method_name"
            assert first_entry["execution_time_seconds"] == 0.0086, "Wrong execution_time"
            assert first_entry["success"] == True, "Wrong success value"
            
            # Verify hourly summary
            hourly_summary = None
            for line in lines:
                entry = json.loads(line)
                if entry.get("summary_type") == "hourly":
                    hourly_summary = entry
                    break
            
            assert hourly_summary is not None, "Hourly summary not found"
            assert hourly_summary["day"] == 0, "Wrong day in hourly summary"
            assert hourly_summary["slot"] == 10, "Wrong slot in hourly summary"
            assert "total_actions" in hourly_summary, "Missing total_actions"
            assert "total_execution_time_seconds" in hourly_summary, "Missing total_execution_time_seconds"
            
            # Verify daily summary
            daily_summary = None
            for line in lines:
                entry = json.loads(line)
                if entry.get("summary_type") == "daily":
                    daily_summary = entry
                    break
            
            assert daily_summary is not None, "Daily summary not found"
            assert daily_summary["day"] == 0, "Wrong day in daily summary"
            assert "slot" not in daily_summary, "Daily summary should not have slot"
            assert daily_summary["total_actions"] >= 2, "Wrong total_actions in daily summary"
            
            print("✅ All integration tests passed!")
            return 0
            
        except Exception as e:
            print(f"❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            return 1


if __name__ == "__main__":
    sys.exit(test_logging_methods())
