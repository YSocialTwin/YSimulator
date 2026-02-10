"""
Unit tests for GPU selection logging in LLM usage logs.

Tests cover:
- VLLMService.get_gpu_selection_info() method
- CostTracker.log_gpu_selection() method
- GPU info format and content
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Mock dependencies before importing
sys.modules["ray"] = MagicMock()
sys.modules["vllm"] = MagicMock()


class TestGPUSelectionLogging(unittest.TestCase):
    """Test GPU selection logging functionality."""

    def test_cost_tracker_log_gpu_selection(self):
        """Test that CostTracker can log GPU selection information."""
        from YSimulator.YClient.llm_utils.cost_tracker import CostTracker

        # Create a temporary log file
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_llm_usage.log"

            # Create cost tracker with file logging
            tracker = CostTracker(
                token_costs=None,
                log_file_path=log_file,
                enable_file_logging=True,
            )

            # Test GPU selection info
            gpu_info = {
                "physical_gpu_id": 2,
                "logical_gpu_id": 0,
                "assignment_method": "dynamic_selection",
                "cuda_visible_devices": "2",
            }

            # Log GPU selection
            tracker.log_gpu_selection(gpu_info, model_name="meta-llama/Llama-3.2-3B", backend="vllm")

            # Verify log file was created
            self.assertTrue(log_file.exists(), "Log file should be created")

            # Read and verify log content
            with open(log_file, "r") as f:
                log_lines = f.readlines()

            self.assertEqual(len(log_lines), 1, "Should have one log entry")

            # Parse JSON log entry
            log_entry = json.loads(log_lines[0])

            # Verify log entry contents
            self.assertEqual(log_entry["event"], "gpu_selection")
            self.assertEqual(log_entry["backend"], "vllm")
            self.assertEqual(log_entry["physical_gpu_id"], 2)
            self.assertEqual(log_entry["logical_gpu_id"], 0)
            self.assertEqual(log_entry["assignment_method"], "dynamic_selection")
            self.assertEqual(log_entry["cuda_visible_devices"], "2")
            self.assertEqual(log_entry["model"], "meta-llama/Llama-3.2-3B")
            self.assertIn("timestamp", log_entry)

    def test_cost_tracker_log_gpu_selection_without_model(self):
        """Test GPU selection logging without model name."""
        from YSimulator.YClient.llm_utils.cost_tracker import CostTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_llm_usage.log"

            tracker = CostTracker(
                token_costs=None,
                log_file_path=log_file,
                enable_file_logging=True,
            )

            gpu_info = {
                "physical_gpu_id": 1,
                "logical_gpu_id": 0,
                "assignment_method": "ray_assigned",
                "cuda_visible_devices": "1",
            }

            # Log without model name
            tracker.log_gpu_selection(gpu_info)

            # Read and verify log content
            with open(log_file, "r") as f:
                log_lines = f.readlines()

            log_entry = json.loads(log_lines[0])

            # Verify model is not in entry when not provided
            self.assertNotIn("model", log_entry)
            self.assertEqual(log_entry["backend"], "vllm")  # default backend

    def test_cost_tracker_gpu_logging_disabled(self):
        """Test that GPU logging is skipped when file logging is disabled."""
        from YSimulator.YClient.llm_utils.cost_tracker import CostTracker

        # Create tracker without file logging
        tracker = CostTracker(
            token_costs=None,
            enable_file_logging=False,
        )

        gpu_info = {
            "physical_gpu_id": 0,
            "logical_gpu_id": 0,
            "assignment_method": "default",
        }

        # Should not raise an exception
        tracker.log_gpu_selection(gpu_info)

    def test_vllm_service_has_gpu_selection_method(self):
        """Test that VLLMService has get_gpu_selection_info method."""
        from YSimulator.YClient.LLM_interactions import vllm_service

        # Check method exists
        self.assertTrue(
            hasattr(vllm_service.VLLMService, "get_gpu_selection_info"),
            "VLLMService should have get_gpu_selection_info method",
        )

    def test_gpu_selection_info_structure(self):
        """Test that GPU selection info has the expected structure."""
        # This test verifies the expected structure without actually creating a VLLMService
        expected_keys = {
            "physical_gpu_id",
            "logical_gpu_id",
            "assignment_method",
            "cuda_visible_devices",
        }

        # Simulate the structure we expect
        gpu_info = {
            "physical_gpu_id": 1,
            "logical_gpu_id": 0,
            "assignment_method": "dynamic_selection",
            "cuda_visible_devices": "1",
        }

        # Verify all expected keys are present
        self.assertEqual(set(gpu_info.keys()), expected_keys)

        # Verify types
        self.assertIsInstance(gpu_info["physical_gpu_id"], (int, type(None)))
        self.assertIsInstance(gpu_info["logical_gpu_id"], (int, type(None)))
        self.assertIsInstance(gpu_info["assignment_method"], str)
        self.assertIsInstance(gpu_info["cuda_visible_devices"], (str, type(None)))


class TestGPUInfoFormatting(unittest.TestCase):
    """Test GPU info formatting and content."""

    def test_assignment_method_values(self):
        """Test that assignment_method has expected values."""
        valid_methods = {"ray_assigned", "dynamic_selection", "default"}

        # Test each valid method
        for method in valid_methods:
            gpu_info = {
                "physical_gpu_id": 0,
                "logical_gpu_id": 0,
                "assignment_method": method,
                "cuda_visible_devices": "0",
            }

            self.assertIn(gpu_info["assignment_method"], valid_methods)

    def test_log_entry_timestamp_format(self):
        """Test that timestamp is in ISO format."""
        from datetime import datetime

        from YSimulator.YClient.llm_utils.cost_tracker import CostTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_llm_usage.log"

            tracker = CostTracker(
                token_costs=None,
                log_file_path=log_file,
                enable_file_logging=True,
            )

            gpu_info = {
                "physical_gpu_id": 0,
                "logical_gpu_id": 0,
                "assignment_method": "default",
                "cuda_visible_devices": None,
            }

            tracker.log_gpu_selection(gpu_info)

            with open(log_file, "r") as f:
                log_entry = json.loads(f.readline())

            # Verify timestamp can be parsed
            timestamp_str = log_entry["timestamp"]
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            self.assertIsInstance(timestamp, datetime)


if __name__ == "__main__":
    unittest.main()
