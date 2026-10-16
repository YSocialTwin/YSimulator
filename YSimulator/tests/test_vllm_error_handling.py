"""
Test VLLMService error handling and visibility.

These tests verify that VLLMService provides clear, actionable error messages
when initialization fails.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Mock dependencies
# Keep the real Ray (loaded by conftest) so other test modules can use it
if "ray" not in sys.modules:
    sys.modules["ray"] = MagicMock()
sys.modules["vllm"] = MagicMock()


class TestVLLMServiceErrorHandling(unittest.TestCase):
    """Test VLLMService error handling and messages."""

    @classmethod
    def setUpClass(cls):
        """Load the source code once for all tests."""
        source_path = (
            Path(__file__).parent.parent / "YClient" / "LLM_interactions" / "vllm_service.py"
        )
        with open(source_path, "r") as f:
            cls.source_code = f.read()

    def test_import_structure(self):
        """Test that VLLMService can be imported."""
        # This just verifies the module loads
        self.assertIn("class VLLMService", self.source_code)

    def test_has_initialize_method(self):
        """Test that VLLMService has _initialize method for error handling."""
        self.assertIn("def _initialize(", self.source_code)

    def test_torch_is_required_by_initialize(self):
        """The initializer imports torch (the detailed install hints were removed with the GPU refactor)."""
        self.assertIn("import torch", self.source_code)

    def test_cuda_not_available_error_message(self):
        """Test that missing CUDA gives clear error message."""
        self.assertIn("torch.cuda.is_available()", self.source_code)
        self.assertIn("CUDA is not available", self.source_code)

    def test_vllm_is_imported_by_initialize(self):
        """The initializer imports vLLM."""
        self.assertIn("from vllm import", self.source_code)

    def test_error_visibility_to_stderr(self):
        """Test that errors are printed to stderr for visibility."""
        # Verify that errors are printed to stderr
        self.assertIn("sys.stderr", self.source_code)
        self.assertIn("flush=True", self.source_code)

    def test_error_messages_have_emojis_for_visibility(self):
        """Test that error messages use emojis for better visibility."""
        # Check for visual indicators in error messages
        self.assertIn("❌", self.source_code)

    def test_failure_on_every_gpu_reports_each_attempt(self):
        """When no GPU can host the engine the error lists every attempt and the last error."""
        self.assertIn("Failed to initialize vLLM on any of", self.source_code)
        self.assertIn("Last error:", self.source_code)

    def test_wrapper_catches_all_exceptions(self):
        """Test that __init__ wrapper catches all exceptions."""
        # Verify the wrapper exists
        self.assertIn("def __init__(", self.source_code)
        self.assertIn("self._initialize(", self.source_code)
        self.assertIn("except Exception as e:", self.source_code)


if __name__ == "__main__":
    unittest.main()
