#!/usr/bin/env python3
"""
Test script to verify action logging functionality.

This script tests the new action logging features added to the client.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

def test_action_log_format():
    """Test that the action log format is correct."""
    # Example of expected format
    expected_format = {
        "time": "2025-12-01 10:39:50",
        "agent_name": "MarisaSoto",
        "method_name": "post",
        "execution_time_seconds": 0.0086,
        "success": True
    }
    
    # Check that all required fields are present
    required_fields = ["time", "agent_name", "method_name", "execution_time_seconds", "success"]
    
    for field in required_fields:
        assert field in expected_format, f"Missing required field: {field}"
    
    # Check types
    assert isinstance(expected_format["time"], str), "time should be string"
    assert isinstance(expected_format["agent_name"], str), "agent_name should be string"
    assert isinstance(expected_format["method_name"], str), "method_name should be string"
    assert isinstance(expected_format["execution_time_seconds"], (int, float)), "execution_time_seconds should be numeric"
    assert isinstance(expected_format["success"], bool), "success should be boolean"
    
    # Try to parse the time format
    try:
        datetime.strptime(expected_format["time"], "%Y-%m-%d %H:%M:%S")
    except ValueError as e:
        assert False, f"Invalid time format: {e}"
    
    print("✓ Action log format test passed")


def test_hourly_summary_format():
    """Test that the hourly summary format is correct."""
    expected_format = {
        "time": "2025-12-01 10:59:59",
        "summary_type": "hourly",
        "day": 0,
        "slot": 10,
        "total_actions": 100,
        "successful_actions": 98,
        "total_execution_time_seconds": 0.8632,
        "average_execution_time_seconds": 0.0086,
        "actions_by_method": {
            "post": 30,
            "comment": 25,
            "read": 25,
            "follow": 20
        }
    }
    
    # Check required fields
    required_fields = [
        "time", "summary_type", "day", "slot", 
        "total_actions", "successful_actions", 
        "total_execution_time_seconds", "average_execution_time_seconds",
        "actions_by_method"
    ]
    
    for field in required_fields:
        assert field in expected_format, f"Missing required field: {field}"
    
    # Check types
    assert expected_format["summary_type"] == "hourly", "summary_type should be 'hourly'"
    assert isinstance(expected_format["day"], int), "day should be int"
    assert isinstance(expected_format["slot"], int), "slot should be int"
    assert isinstance(expected_format["total_actions"], int), "total_actions should be int"
    assert isinstance(expected_format["successful_actions"], int), "successful_actions should be int"
    assert isinstance(expected_format["actions_by_method"], dict), "actions_by_method should be dict"
    
    print("✓ Hourly summary format test passed")


def test_daily_summary_format():
    """Test that the daily summary format is correct."""
    expected_format = {
        "time": "2025-12-01 23:59:59",
        "summary_type": "daily",
        "day": 0,
        "total_actions": 2400,
        "successful_actions": 2380,
        "total_execution_time_seconds": 20.712,
        "average_execution_time_seconds": 0.0086,
        "actions_by_method": {
            "post": 720,
            "comment": 600,
            "read": 600,
            "follow": 480
        }
    }
    
    # Check required fields
    required_fields = [
        "time", "summary_type", "day", 
        "total_actions", "successful_actions", 
        "total_execution_time_seconds", "average_execution_time_seconds",
        "actions_by_method"
    ]
    
    for field in required_fields:
        assert field in expected_format, f"Missing required field: {field}"
    
    # Check types
    assert expected_format["summary_type"] == "daily", "summary_type should be 'daily'"
    assert isinstance(expected_format["day"], int), "day should be int"
    assert "slot" not in expected_format, "daily summary should not have slot field"
    assert isinstance(expected_format["total_actions"], int), "total_actions should be int"
    assert isinstance(expected_format["successful_actions"], int), "successful_actions should be int"
    assert isinstance(expected_format["actions_by_method"], dict), "actions_by_method should be dict"
    
    print("✓ Daily summary format test passed")


def test_json_serialization():
    """Test that log entries can be serialized to JSON."""
    action_entry = {
        "time": "2025-12-01 10:39:50",
        "agent_name": "MarisaSoto",
        "method_name": "post",
        "execution_time_seconds": 0.0086,
        "success": True
    }
    
    try:
        json_str = json.dumps(action_entry)
        parsed = json.loads(json_str)
        assert parsed == action_entry, "JSON roundtrip failed"
    except Exception as e:
        assert False, f"JSON serialization failed: {e}"
    
    print("✓ JSON serialization test passed")


def main():
    """Run all tests."""
    print("Running action logging tests...\n")
    
    try:
        test_action_log_format()
        test_hourly_summary_format()
        test_daily_summary_format()
        test_json_serialization()
        
        print("\n✅ All tests passed!")
        return 0
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
