"""
Test to verify that LLM usage logs are written immediately.
"""

import json
import tempfile
import unittest
from pathlib import Path

from YSimulator.YClient.llm_utils.cost_tracker import CostTracker


class TestImmediateLogging(unittest.TestCase):
    """Test that logs are written immediately, not buffered."""

    def test_log_written_immediately_after_record_call(self):
        """Test that record_call writes to file immediately."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_llm_usage.log"

            # Create cost tracker
            tracker = CostTracker(
                token_costs=None,
                log_file_path=log_file,
                enable_file_logging=True,
            )

            # Record a call
            tracker.record_call("test_method", input_tokens=10, output_tokens=20)

            # Verify log file exists and has content
            self.assertTrue(log_file.exists(), "Log file should exist")

            # Read and verify content immediately (without closing tracker)
            with open(log_file, "r") as f:
                content = f.read()

            self.assertGreater(len(content), 0, "Log file should have content")

            # Parse and verify JSON
            lines = content.strip().split("\n")
            self.assertEqual(len(lines), 1, "Should have one log entry")

            entry = json.loads(lines[0])
            self.assertEqual(entry["method"], "test_method")
            self.assertEqual(entry["input_tokens"], 10)
            self.assertEqual(entry["output_tokens"], 20)
            self.assertEqual(entry["total_tokens"], 30)

    def test_gpu_selection_log_written_immediately(self):
        """Test that GPU selection log is written immediately."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_llm_usage.log"

            # Create cost tracker
            tracker = CostTracker(
                token_costs=None,
                log_file_path=log_file,
                enable_file_logging=True,
            )

            # Log GPU selection
            gpu_info = {
                "physical_gpu_id": 1,
                "logical_gpu_id": 0,
                "assignment_method": "dynamic_selection",
                "cuda_visible_devices": "1",
            }
            tracker.log_gpu_selection(gpu_info, model_name="test-model", backend="vllm")

            # Verify log file exists and has content
            self.assertTrue(log_file.exists(), "Log file should exist")

            # Read and verify content immediately
            with open(log_file, "r") as f:
                content = f.read()

            self.assertGreater(len(content), 0, "Log file should have content")

            # Parse and verify JSON
            lines = content.strip().split("\n")
            self.assertEqual(len(lines), 1, "Should have one log entry")

            entry = json.loads(lines[0])
            self.assertEqual(entry["event"], "gpu_selection")
            self.assertEqual(entry["physical_gpu_id"], 1)
            self.assertEqual(entry["assignment_method"], "dynamic_selection")
            self.assertEqual(entry["model"], "test-model")

    def test_multiple_logs_written_immediately(self):
        """Test that multiple log entries are written immediately."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_llm_usage.log"

            # Create cost tracker
            tracker = CostTracker(
                token_costs=None,
                log_file_path=log_file,
                enable_file_logging=True,
            )

            # Log GPU selection
            gpu_info = {
                "physical_gpu_id": 0,
                "logical_gpu_id": 0,
                "assignment_method": "default",
            }
            tracker.log_gpu_selection(gpu_info)

            # Record multiple calls
            tracker.record_call("method1", input_tokens=10, output_tokens=5)
            tracker.record_call("method2", input_tokens=20, output_tokens=15)

            # Verify all logs are written
            with open(log_file, "r") as f:
                content = f.read()

            lines = content.strip().split("\n")
            self.assertEqual(len(lines), 3, "Should have three log entries")

            # Verify first entry is GPU selection
            entry1 = json.loads(lines[0])
            self.assertEqual(entry1["event"], "gpu_selection")

            # Verify second and third entries are method calls
            entry2 = json.loads(lines[1])
            self.assertEqual(entry2["method"], "method1")

            entry3 = json.loads(lines[2])
            self.assertEqual(entry3["method"], "method2")


if __name__ == "__main__":
    unittest.main()
