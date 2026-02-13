"""
Unit tests for GPU utility functions.

Tests cover:
- GPU memory querying
- GPU selection logic
- Ray GPU assignment detection
- Memory requirement estimation
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock torch before importing gpu_utils
sys.modules["torch"] = MagicMock()
sys.modules["torch.cuda"] = MagicMock()

# Test tolerance for memory estimation (10% tolerance for rounding and estimation errors)
MEMORY_ESTIMATION_TOLERANCE = 0.1


class TestGPUMemoryInfo(unittest.TestCase):
    """Test GPU memory information functions."""

    @patch("YSimulator.YClient.llm_utils.gpu_utils.torch")
    def test_get_gpu_memory_info(self, mock_torch):
        """Test getting memory info for a single GPU."""
        # Mock CUDA availability
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.return_value = 2
        mock_torch.cuda.mem_get_info.return_value = (
            10 * 1024**3,  # 10 GB free
            40 * 1024**3,  # 40 GB total
        )

        from YSimulator.YClient.llm_utils.gpu_utils import get_gpu_memory_info

        free_gb, total_gb = get_gpu_memory_info(device_id=0)

        self.assertAlmostEqual(free_gb, 10.0, places=1)
        self.assertAlmostEqual(total_gb, 40.0, places=1)
        mock_torch.cuda.mem_get_info.assert_called_once_with(0)

    @patch("YSimulator.YClient.llm_utils.gpu_utils.torch")
    def test_get_gpu_memory_info_no_cuda(self, mock_torch):
        """Test error when CUDA is not available."""
        mock_torch.cuda.is_available.return_value = False

        from YSimulator.YClient.llm_utils.gpu_utils import get_gpu_memory_info

        with self.assertRaises(RuntimeError) as cm:
            get_gpu_memory_info(device_id=0)

        self.assertIn("CUDA is not available", str(cm.exception))

    @patch("YSimulator.YClient.llm_utils.gpu_utils.torch")
    def test_get_all_gpu_memory_info(self, mock_torch):
        """Test getting memory info for all GPUs."""
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.return_value = 2

        # Mock different memory for each GPU
        def mock_mem_get_info(device_id):
            if device_id == 0:
                return (5 * 1024**3, 40 * 1024**3)  # 5/40 GB
            else:
                return (15 * 1024**3, 40 * 1024**3)  # 15/40 GB

        mock_torch.cuda.mem_get_info.side_effect = mock_mem_get_info

        from YSimulator.YClient.llm_utils.gpu_utils import get_all_gpu_memory_info

        gpu_info = get_all_gpu_memory_info()

        self.assertEqual(len(gpu_info), 2)
        self.assertEqual(gpu_info[0][0], 0)  # device_id
        self.assertAlmostEqual(gpu_info[0][1], 5.0, places=1)  # free GB
        self.assertEqual(gpu_info[1][0], 1)
        self.assertAlmostEqual(gpu_info[1][1], 15.0, places=1)


class TestGPUSelection(unittest.TestCase):
    """Test GPU selection functions."""

    @patch("YSimulator.YClient.llm_utils.gpu_utils.get_all_gpu_memory_info")
    def test_select_gpu_with_most_free_memory(self, mock_get_all):
        """Test selecting GPU with most free memory."""
        mock_get_all.return_value = [
            (0, 5.0, 40.0),  # GPU 0: 5 GB free
            (1, 15.0, 40.0),  # GPU 1: 15 GB free
            (2, 10.0, 40.0),  # GPU 2: 10 GB free
        ]

        from YSimulator.YClient.llm_utils.gpu_utils import select_gpu_with_most_free_memory

        gpu_id = select_gpu_with_most_free_memory()

        self.assertEqual(gpu_id, 1)  # Should select GPU 1 with 15 GB free

    @patch("YSimulator.YClient.llm_utils.gpu_utils.get_all_gpu_memory_info")
    def test_select_gpu_with_sufficient_memory_found(self, mock_get_all):
        """Test selecting GPU with sufficient memory when available."""
        mock_get_all.return_value = [
            (0, 5.0, 40.0),  # GPU 0: 5 GB free - not enough
            (1, 15.0, 40.0),  # GPU 1: 15 GB free - sufficient
            (2, 10.0, 40.0),  # GPU 2: 10 GB free - sufficient
        ]

        from YSimulator.YClient.llm_utils.gpu_utils import select_gpu_with_sufficient_memory

        gpu_id = select_gpu_with_sufficient_memory(required_memory_gb=8.0)

        # Should select GPU 1 (most free among sufficient options)
        self.assertEqual(gpu_id, 1)

    @patch("YSimulator.YClient.llm_utils.gpu_utils.get_all_gpu_memory_info")
    def test_select_gpu_with_sufficient_memory_not_found(self, mock_get_all):
        """Test selecting GPU when no GPU has sufficient memory."""
        mock_get_all.return_value = [
            (0, 5.0, 40.0),  # GPU 0: 5 GB free
            (1, 7.0, 40.0),  # GPU 1: 7 GB free
        ]

        from YSimulator.YClient.llm_utils.gpu_utils import select_gpu_with_sufficient_memory

        gpu_id = select_gpu_with_sufficient_memory(required_memory_gb=10.0)

        # Should return None when no GPU has sufficient memory
        self.assertIsNone(gpu_id)


class TestRayGPUAssignment(unittest.TestCase):
    """Test Ray GPU assignment detection."""

    def test_get_ray_assigned_gpu_set(self):
        """Test detecting Ray-assigned GPU when CUDA_VISIBLE_DEVICES is set."""
        # Save original value
        original = os.environ.get("CUDA_VISIBLE_DEVICES")

        try:
            os.environ["CUDA_VISIBLE_DEVICES"] = "3"

            from YSimulator.YClient.llm_utils.gpu_utils import get_ray_assigned_gpu

            gpu_id = get_ray_assigned_gpu()

            # Ray assigns GPU 3, which becomes device 0 within the actor
            self.assertEqual(gpu_id, 0)
        finally:
            # Restore original value
            if original is not None:
                os.environ["CUDA_VISIBLE_DEVICES"] = original
            elif "CUDA_VISIBLE_DEVICES" in os.environ:
                del os.environ["CUDA_VISIBLE_DEVICES"]

    def test_get_ray_assigned_gpu_not_set(self):
        """Test when Ray has not assigned a GPU."""
        # Save original value
        original = os.environ.get("CUDA_VISIBLE_DEVICES")

        try:
            if "CUDA_VISIBLE_DEVICES" in os.environ:
                del os.environ["CUDA_VISIBLE_DEVICES"]

            from YSimulator.YClient.llm_utils.gpu_utils import get_ray_assigned_gpu

            gpu_id = get_ray_assigned_gpu()

            self.assertIsNone(gpu_id)
        finally:
            # Restore original value
            if original is not None:
                os.environ["CUDA_VISIBLE_DEVICES"] = original

    def test_get_ray_assigned_gpu_multiple(self):
        """Test when Ray assigns multiple GPUs."""
        # Save original value
        original = os.environ.get("CUDA_VISIBLE_DEVICES")

        try:
            os.environ["CUDA_VISIBLE_DEVICES"] = "2,3"

            from YSimulator.YClient.llm_utils.gpu_utils import get_ray_assigned_gpu

            gpu_id = get_ray_assigned_gpu()

            # Should still return 0 (first visible device)
            self.assertEqual(gpu_id, 0)
        finally:
            # Restore original value
            if original is not None:
                os.environ["CUDA_VISIBLE_DEVICES"] = original
            elif "CUDA_VISIBLE_DEVICES" in os.environ:
                del os.environ["CUDA_VISIBLE_DEVICES"]


class TestMemoryEstimation(unittest.TestCase):
    """Test memory requirement estimation."""

    def test_estimate_required_vllm_memory_3b(self):
        """Test memory estimation for 3B model."""
        from YSimulator.YClient.llm_utils.gpu_utils import estimate_required_vllm_memory

        required_gb = estimate_required_vllm_memory(
            model_name="meta-llama/Llama-3.2-3B",
            max_model_len=40000,
            gpu_memory_utilization=0.9,
        )

        # Expected calculation for 3B model:
        # params = 3B, base_memory = (3 * 2) * 1.5 = 9 GB
        # length_factor = 1.0 + (40000/40000) * 0.3 = 1.3
        # estimated = 9 * 1.3 = 11.7 GB
        # required = 11.7 / 0.9 = 13.0 GB
        expected_gb = ((3 * 2) * 1.5) * (1.0 + (40000 / 40000) * 0.3) / 0.9

        # Allow tolerance for rounding
        self.assertAlmostEqual(
            required_gb, expected_gb, delta=expected_gb * MEMORY_ESTIMATION_TOLERANCE
        )

    def test_estimate_required_vllm_memory_7b(self):
        """Test memory estimation for 7B model."""
        from YSimulator.YClient.llm_utils.gpu_utils import estimate_required_vllm_memory

        required_gb = estimate_required_vllm_memory(
            model_name="mistralai/Mistral-7B-v0.1",
            max_model_len=40000,
            gpu_memory_utilization=0.9,
        )

        # Expected calculation for 7B model:
        # params = 7B, base_memory = (7 * 2) * 1.5 = 21 GB
        # length_factor = 1.0 + (40000/40000) * 0.3 = 1.3
        # estimated = 21 * 1.3 = 27.3 GB
        # required = 27.3 / 0.9 = 30.33 GB
        expected_gb = ((7 * 2) * 1.5) * (1.0 + (40000 / 40000) * 0.3) / 0.9

        # Allow tolerance for rounding
        self.assertAlmostEqual(
            required_gb, expected_gb, delta=expected_gb * MEMORY_ESTIMATION_TOLERANCE
        )

    def test_estimate_required_vllm_memory_unknown_model(self):
        """Test memory estimation for unknown model (should use conservative default)."""
        from YSimulator.YClient.llm_utils.gpu_utils import estimate_required_vllm_memory

        required_gb = estimate_required_vllm_memory(
            model_name="unknown/custom-model",
            max_model_len=40000,
            gpu_memory_utilization=0.9,
        )

        # Should default to 7B estimate
        # params = 7B, base_memory = (7 * 2) * 1.5 = 21 GB
        # length_factor = 1.0 + (40000/40000) * 0.3 = 1.3
        # estimated = 21 * 1.3 = 27.3 GB
        # required = 27.3 / 0.9 = 30.33 GB
        expected_gb = ((7 * 2) * 1.5) * (1.0 + (40000 / 40000) * 0.3) / 0.9

        # Allow tolerance for rounding
        self.assertAlmostEqual(
            required_gb, expected_gb, delta=expected_gb * MEMORY_ESTIMATION_TOLERANCE
        )


class TestGPUCount(unittest.TestCase):
    """Test GPU count detection."""

    @patch("YSimulator.YClient.llm_utils.gpu_utils.torch")
    def test_get_total_gpu_count(self, mock_torch):
        """Test getting total GPU count."""
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.return_value = 4

        from YSimulator.YClient.llm_utils.gpu_utils import get_total_gpu_count

        count = get_total_gpu_count()

        self.assertEqual(count, 4)

    @patch("YSimulator.YClient.llm_utils.gpu_utils.torch")
    def test_get_total_gpu_count_no_cuda(self, mock_torch):
        """Test getting GPU count when CUDA is not available."""
        mock_torch.cuda.is_available.return_value = False

        from YSimulator.YClient.llm_utils.gpu_utils import get_total_gpu_count

        count = get_total_gpu_count()

        self.assertEqual(count, 0)


class TestDedicatedGPUSelection(unittest.TestCase):
    """Test dedicated GPU selection for vision models."""

    @patch("YSimulator.YClient.llm_utils.gpu_utils.get_ordered_gpus_by_memory")
    def test_select_dedicated_gpu_for_vision(self, mock_get_ordered):
        """Test selecting dedicated GPU excluding specific GPUs."""
        mock_get_ordered.return_value = [
            (0, 30.0, 40.0),  # GPU 0: 30 GB free (text generation GPU)
            (1, 25.0, 40.0),  # GPU 1: 25 GB free
            (2, 20.0, 40.0),  # GPU 2: 20 GB free
        ]

        from YSimulator.YClient.llm_utils.gpu_utils import select_dedicated_gpu_for_vision

        # Exclude GPU 0 (used for text generation)
        gpu_id = select_dedicated_gpu_for_vision(required_memory_gb=10.0, exclude_gpus=[0])

        # Should select GPU 1 (most free memory excluding GPU 0)
        self.assertEqual(gpu_id, 1)

    @patch("YSimulator.YClient.llm_utils.gpu_utils.get_ordered_gpus_by_memory")
    def test_select_dedicated_gpu_for_vision_no_exclusion(self, mock_get_ordered):
        """Test selecting dedicated GPU without exclusions."""
        mock_get_ordered.return_value = [
            (0, 30.0, 40.0),  # GPU 0: 30 GB free
            (1, 25.0, 40.0),  # GPU 1: 25 GB free
        ]

        from YSimulator.YClient.llm_utils.gpu_utils import select_dedicated_gpu_for_vision

        # No exclusions
        gpu_id = select_dedicated_gpu_for_vision(required_memory_gb=10.0)

        # Should select GPU 0 (most free memory)
        self.assertEqual(gpu_id, 0)

    @patch("YSimulator.YClient.llm_utils.gpu_utils.get_ordered_gpus_by_memory")
    def test_select_dedicated_gpu_for_vision_all_excluded(self, mock_get_ordered):
        """Test selecting dedicated GPU when all suitable GPUs are excluded."""
        mock_get_ordered.return_value = [
            (0, 30.0, 40.0),  # GPU 0: 30 GB free
            (1, 25.0, 40.0),  # GPU 1: 25 GB free
        ]

        from YSimulator.YClient.llm_utils.gpu_utils import select_dedicated_gpu_for_vision

        # Exclude all GPUs
        gpu_id = select_dedicated_gpu_for_vision(required_memory_gb=10.0, exclude_gpus=[0, 1])

        # Should return None when all GPUs are excluded
        self.assertIsNone(gpu_id)

    @patch("YSimulator.YClient.llm_utils.gpu_utils.get_ordered_gpus_by_memory")
    def test_select_dedicated_gpu_for_vision_insufficient_memory(self, mock_get_ordered):
        """Test selecting dedicated GPU when no GPU has sufficient memory."""
        mock_get_ordered.return_value = []  # No GPUs with sufficient memory

        from YSimulator.YClient.llm_utils.gpu_utils import select_dedicated_gpu_for_vision

        gpu_id = select_dedicated_gpu_for_vision(required_memory_gb=50.0)

        # Should return None when no GPU has sufficient memory
        self.assertIsNone(gpu_id)


if __name__ == "__main__":
    unittest.main()
