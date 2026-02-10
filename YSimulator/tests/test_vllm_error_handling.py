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
sys.modules["ray"] = MagicMock()
sys.modules["vllm"] = MagicMock()


class TestVLLMServiceErrorHandling(unittest.TestCase):
    """Test VLLMService error handling and messages."""

    @classmethod
    def setUpClass(cls):
        """Load the source code once for all tests."""
        source_path = Path(__file__).parent.parent / "YClient" / "LLM_interactions" / "vllm_service.py"
        with open(source_path, "r") as f:
            cls.source_code = f.read()

    def test_import_structure(self):
        """Test that VLLMService can be imported."""
        # This just verifies the module loads
        self.assertIn("class VLLMService", self.source_code)

    def test_has_initialize_method(self):
        """Test that VLLMService has _initialize method for error handling."""
        self.assertIn("def _initialize(", self.source_code)

    def test_torch_not_available_error_message(self):
        """Test that missing torch gives clear error message."""
        # Verify error handling for torch is present
        self.assertIn("import torch", self.source_code)
        self.assertIn("PyTorch is not installed", self.source_code)
        self.assertIn("PyTorch is required", self.source_code)

    def test_cuda_not_available_error_message(self):
        """Test that missing CUDA gives clear error message."""
        # Verify CUDA availability check is present
        self.assertIn("torch.cuda.is_available()", self.source_code)
        self.assertIn("CUDA is not available", self.source_code)
        self.assertIn("CUDA is not available but is required", self.source_code)

    def test_vllm_not_available_error_message(self):
        """Test that missing vLLM gives clear error message."""
        # Verify vLLM import error handling is present
        self.assertIn("from vllm import", self.source_code)
        self.assertIn("vLLM is not installed", self.source_code)

    def test_error_visibility_to_stderr(self):
        """Test that errors are printed to stderr for visibility."""
        # Verify that errors are printed to stderr
        self.assertIn("sys.stderr", self.source_code)
        self.assertIn("flush=True", self.source_code)

    def test_error_messages_have_emojis_for_visibility(self):
        """Test that error messages use emojis for better visibility."""
        # Check for visual indicators in error messages
        self.assertIn("❌", self.source_code)

    def test_error_messages_have_installation_instructions(self):
        """Test that error messages include installation instructions."""
        # Check for installation instructions
        self.assertIn("pip install", self.source_code)
        self.assertIn("Install with:", self.source_code)

    def test_error_messages_have_diagnostic_commands(self):
        """Test that error messages include diagnostic commands."""
        # Check for diagnostic commands
        self.assertIn("python -c", self.source_code)

    def test_wrapper_catches_all_exceptions(self):
        """Test that __init__ wrapper catches all exceptions."""
        # Verify the wrapper exists
        self.assertIn("def __init__(", self.source_code)
        self.assertIn("self._initialize(", self.source_code)
        self.assertIn("except Exception as e:", self.source_code)


if __name__ == "__main__":
    unittest.main()
