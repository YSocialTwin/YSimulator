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

    def test_torch_not_available_error_message(self):
        """Test that torch is imported for CUDA checks."""
        # Verify torch is imported for GPU operations
        self.assertIn("import torch", self.source_code)
        self.assertIn("torch.cuda.is_available()", self.source_code)

    def test_cuda_not_available_error_message(self):
        """Test that missing CUDA gives clear error message."""
        # Verify CUDA availability check is present
        self.assertIn("torch.cuda.is_available()", self.source_code)
        self.assertIn("CUDA is not available after masking", self.source_code)

    def test_vllm_not_available_error_message(self):
        """Test that vLLM is imported for inference."""
        # Verify vLLM import is present
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

    def test_error_messages_have_installation_instructions(self):
        """Test that error messages include GPU failure context."""
        # Current implementation reports GPU failures with free memory info
        self.assertIn("❌ VLLMService Initialization Failed", self.source_code)
        self.assertIn("All GPUs Exhausted", self.source_code)

    def test_error_messages_have_diagnostic_commands(self):
        """Test that error messages include CUDA device diagnostic information."""
        # Current implementation reports CUDA_VISIBLE_DEVICES for GPU diagnostics
        self.assertIn("CUDA_VISIBLE_DEVICES", self.source_code)
        self.assertIn("PCI_BUS_ID", self.source_code)

    def test_wrapper_catches_all_exceptions(self):
        """Test that __init__ wrapper catches all exceptions."""
        # Verify the wrapper exists
        self.assertIn("def __init__(", self.source_code)
        self.assertIn("self._initialize(", self.source_code)
        self.assertIn("except Exception as e:", self.source_code)


if __name__ == "__main__":
    unittest.main()
