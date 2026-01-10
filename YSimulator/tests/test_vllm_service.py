"""
Unit tests for vLLM Service.

Tests cover:
- VLLMService initialization
- Batch inference capabilities  
- Compatibility with LLMService interface
- Configuration validation

Note: These tests verify the vLLM service structure and interface compatibility.
Full integration tests require a GPU-enabled environment with vLLM installed.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock dependencies before importing vllm_service
sys.modules["ray"] = MagicMock()
sys.modules["vllm"] = MagicMock()


class TestVLLMServiceConfiguration(unittest.TestCase):
    """Test VLLMService configuration and interface."""

    def test_vllm_service_exists(self):
        """Test that VLLMService module can be imported."""
        try:
            from YSimulator.YClient.LLM_interactions import vllm_service

            self.assertTrue(hasattr(vllm_service, "VLLMService"))
        except ImportError as e:
            self.fail(f"Failed to import vllm_service: {e}")

    def test_vllm_service_has_required_methods(self):
        """Test that VLLMService has all required methods for LLMService compatibility."""
        from YSimulator.YClient.LLM_interactions import vllm_service

        required_methods = [
            "generate_post",
            "generate_post_batch",
            "decide_reaction",
            "generate_comment",
            "generate_news_commentary",
            "generate_share_commentary",
            "generate_read_reaction",
            "generate_follow_decision",
            "decide_search_action",
            "generate_secondary_follow_decision",
            "extract_topics_from_article",
            "extract_emotions",
            "describe_image",
            "infer_article_opinion",
            "generate_image_commentary",
            "evaluate_opinion",
        ]

        # Read the source file directly to check for method definitions
        import inspect

        source = inspect.getsource(vllm_service)

        for method in required_methods:
            self.assertIn(
                f"def {method}(",
                source,
                f"VLLMService is missing required method: {method}",
            )

    def test_batch_method_exists(self):
        """Test that VLLMService has batch processing method."""
        from YSimulator.YClient.LLM_interactions import vllm_service

        import inspect

        source = inspect.getsource(vllm_service)

        self.assertIn(
            "def generate_post_batch(",
            source,
            "VLLMService is missing generate_post_batch method for batch inference",
        )


class TestVLLMServiceWithLoadBalancer(unittest.TestCase):
    """Test vLLM integration with load balancer."""

    def test_load_balancer_supports_backend_parameter(self):
        """Test that load balancer accepts backend parameter."""
        try:
            from YSimulator.YClient.llm_utils import load_balancer

            import inspect

            # Check create_llm_actors signature
            sig = inspect.signature(load_balancer.create_llm_actors)
            params = sig.parameters

            self.assertIn("backend", params, "create_llm_actors missing backend parameter")

            # Check LLMLoadBalancer __init__ signature
            sig = inspect.signature(load_balancer.LLMLoadBalancer.__init__)
            params = sig.parameters

            self.assertIn("backend", params, "LLMLoadBalancer missing backend parameter")
        except ImportError as e:
            self.fail(f"Failed to import load_balancer: {e}")

    def test_load_balancer_imports_vllm_service(self):
        """Test that load balancer can reference VLLMService."""
        from YSimulator.YClient.llm_utils import load_balancer

        # Verify the load_balancer module references VLLMService
        import inspect

        source = inspect.getsource(load_balancer.LLMLoadBalancer.__init__)
        self.assertIn(
            "VLLMService", source, "LLMLoadBalancer does not import/reference VLLMService"
        )


class TestRunClientIntegration(unittest.TestCase):
    """Test run_client.py integration with vLLM."""

    def test_run_client_imports_vllm_service(self):
        """Test that run_client.py imports VLLMService."""
        with open("/home/runner/work/YSimulator/YSimulator/run_client.py", "r") as f:
            content = f.read()

        self.assertIn(
            "VLLMService",
            content,
            "run_client.py does not import VLLMService",
        )

    def test_run_client_checks_backend_config(self):
        """Test that run_client.py checks for backend configuration."""
        with open("/home/runner/work/YSimulator/YSimulator/run_client.py", "r") as f:
            content = f.read()

        self.assertIn(
            'llm_config.get("backend"',
            content,
            "run_client.py does not check backend configuration",
        )

        self.assertIn(
            "vllm",
            content.lower(),
            "run_client.py does not reference vllm backend",
        )


class TestConfigurationExample(unittest.TestCase):
    """Test vLLM configuration example."""

    def test_vllm_example_exists(self):
        """Test that vLLM example configuration exists."""
        import os

        example_dir = "/home/runner/work/YSimulator/YSimulator/example/llm_population_100_vllm"
        self.assertTrue(os.path.isdir(example_dir), "vLLM example directory does not exist")

        config_file = os.path.join(example_dir, "simulation_config.json")
        self.assertTrue(os.path.isfile(config_file), "simulation_config.json does not exist")

    def test_vllm_example_has_backend_config(self):
        """Test that vLLM example has backend configuration."""
        import json
        import os

        config_file = (
            "/home/runner/work/YSimulator/YSimulator/example/llm_population_100_vllm/simulation_config.json"
        )

        if os.path.isfile(config_file):
            with open(config_file, "r") as f:
                config = json.load(f)

            self.assertIn("llm", config, "Configuration missing llm section")
            self.assertIn(
                "backend", config["llm"], "LLM configuration missing backend field"
            )
            self.assertEqual(
                config["llm"]["backend"],
                "vllm",
                "Backend should be set to vllm in example",
            )


if __name__ == "__main__":
    unittest.main()

