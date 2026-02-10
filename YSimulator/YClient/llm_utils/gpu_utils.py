"""
GPU utility functions for vLLM service.

This module provides utilities for GPU memory checking and device selection
to support dynamic GPU allocation on multi-GPU systems.
"""

import logging
import os
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def get_gpu_memory_info(device_id: int = 0) -> Tuple[float, float]:
    """
    Get memory information for a specific GPU device.

    Args:
        device_id: CUDA device ID to query

    Returns:
        Tuple of (free_memory_gb, total_memory_gb)

    Raises:
        RuntimeError: If unable to query GPU memory
    """
    try:
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available")

        if device_id >= torch.cuda.device_count():
            raise RuntimeError(
                f"Invalid device_id {device_id}. Only {torch.cuda.device_count()} GPUs available"
            )

        # Get memory stats for the device
        free_memory = torch.cuda.mem_get_info(device_id)[0]
        total_memory = torch.cuda.mem_get_info(device_id)[1]

        free_gb = free_memory / (1024**3)
        total_gb = total_memory / (1024**3)

        return free_gb, total_gb
    except ImportError:
        raise RuntimeError("PyTorch is not installed. Cannot query GPU memory.")
    except Exception as e:
        raise RuntimeError(f"Failed to query GPU memory: {e}")


def get_all_gpu_memory_info() -> List[Tuple[int, float, float]]:
    """
    Get memory information for all available GPUs.

    Returns:
        List of tuples (device_id, free_memory_gb, total_memory_gb)

    Raises:
        RuntimeError: If unable to query GPU memory
    """
    try:
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available")

        gpu_info = []
        for device_id in range(torch.cuda.device_count()):
            free_gb, total_gb = get_gpu_memory_info(device_id)
            gpu_info.append((device_id, free_gb, total_gb))

        return gpu_info
    except ImportError:
        raise RuntimeError("PyTorch is not installed. Cannot query GPU memory.")


def select_gpu_with_most_free_memory() -> int:
    """
    Select the GPU with the most free memory.

    Returns:
        Device ID of the GPU with most free memory

    Raises:
        RuntimeError: If no GPUs are available or memory query fails
    """
    try:
        gpu_info = get_all_gpu_memory_info()

        if not gpu_info:
            raise RuntimeError("No GPUs available")

        # Sort by free memory (descending) and return the device with most free memory
        gpu_info.sort(key=lambda x: x[1], reverse=True)
        best_gpu_id = gpu_info[0][0]
        best_free_gb = gpu_info[0][1]

        logger.info(
            f"[GPU Selection] Selected GPU {best_gpu_id} with {best_free_gb:.2f} GB free memory"
        )

        return best_gpu_id
    except Exception as e:
        logger.error(f"[GPU Selection] Failed to select GPU: {e}")
        raise


def select_gpu_with_sufficient_memory(required_memory_gb: float) -> Optional[int]:
    """
    Select a GPU with sufficient free memory.

    Args:
        required_memory_gb: Minimum required free memory in GB

    Returns:
        Device ID of a suitable GPU, or None if no GPU has sufficient memory

    Raises:
        RuntimeError: If unable to query GPU memory
    """
    try:
        gpu_info = get_all_gpu_memory_info()

        if not gpu_info:
            raise RuntimeError("No GPUs available")

        # Filter GPUs with sufficient memory
        suitable_gpus = [
            (device_id, free_gb, total_gb)
            for device_id, free_gb, total_gb in gpu_info
            if free_gb >= required_memory_gb
        ]

        if not suitable_gpus:
            logger.warning(
                f"[GPU Selection] No GPU found with {required_memory_gb:.2f} GB free memory"
            )
            # Log available memory on each GPU
            for device_id, free_gb, total_gb in gpu_info:
                logger.warning(
                    f"[GPU Selection]   GPU {device_id}: {free_gb:.2f}/{total_gb:.2f} GB free"
                )
            return None

        # Sort by free memory (descending) and return the best option
        suitable_gpus.sort(key=lambda x: x[1], reverse=True)
        best_gpu_id = suitable_gpus[0][0]
        best_free_gb = suitable_gpus[0][1]

        logger.info(
            f"[GPU Selection] Selected GPU {best_gpu_id} with {best_free_gb:.2f} GB free "
            f"(required: {required_memory_gb:.2f} GB)"
        )

        return best_gpu_id
    except Exception as e:
        logger.error(f"[GPU Selection] Failed to select GPU: {e}")
        raise


def get_ray_assigned_gpu() -> Optional[int]:
    """
    Get the GPU device ID assigned by Ray to this actor.

    Ray sets CUDA_VISIBLE_DEVICES to control which GPUs are visible to the actor.
    This function detects which GPU Ray has assigned.

    Returns:
        GPU device ID (0-indexed within the visible devices), or None if not set

    Note:
        When Ray assigns a GPU, it sets CUDA_VISIBLE_DEVICES to that specific GPU,
        so within the actor, the assigned GPU will appear as device 0.
    """
    cuda_visible_devices = os.environ.get("CUDA_VISIBLE_DEVICES", None)

    if cuda_visible_devices is None:
        logger.debug("[GPU Selection] CUDA_VISIBLE_DEVICES not set by Ray")
        return None

    # Parse the device IDs
    try:
        device_ids = [int(d.strip()) for d in cuda_visible_devices.split(",") if d.strip()]
        if not device_ids:
            logger.debug("[GPU Selection] CUDA_VISIBLE_DEVICES is empty")
            return None

        # Ray sets CUDA_VISIBLE_DEVICES to the assigned GPU
        # Within the actor, this becomes device 0
        logger.info(
            f"[GPU Selection] Ray assigned GPU(s): {device_ids} "
            f"(visible as device 0 within actor)"
        )
        return 0  # The assigned GPU is visible as device 0 within the actor
    except ValueError as e:
        logger.warning(f"[GPU Selection] Failed to parse CUDA_VISIBLE_DEVICES: {e}")
        return None


def estimate_required_vllm_memory(
    model_name: str,
    max_model_len: int = 40000,
    gpu_memory_utilization: float = 0.9,
) -> float:
    """
    Estimate the required GPU memory for loading a vLLM model.

    This is a rough estimate based on model size. Actual memory usage may vary.

    Args:
        model_name: Name of the model (e.g., "meta-llama/Llama-3.2-3B")
        max_model_len: Maximum sequence length
        gpu_memory_utilization: Target GPU memory utilization

    Returns:
        Estimated required memory in GB
    """
    # Extract parameter count from model name if possible
    # This is a heuristic and may not work for all model names
    model_name_lower = model_name.lower()

    # Common model size patterns
    if "1b" in model_name_lower or "1.5b" in model_name_lower:
        params_billions = 1.5
    elif "3b" in model_name_lower:
        params_billions = 3
    elif "7b" in model_name_lower:
        params_billions = 7
    elif "13b" in model_name_lower:
        params_billions = 13
    elif "30b" in model_name_lower:
        params_billions = 30
    elif "70b" in model_name_lower:
        params_billions = 70
    else:
        # Default to a conservative estimate
        logger.warning(
            f"[GPU Selection] Cannot determine model size from name '{model_name}', "
            f"using conservative estimate of 7B parameters"
        )
        params_billions = 7

    # Rough estimate: ~2 bytes per parameter (FP16) + KV cache + overhead
    # Model weights: params * 2 bytes
    # KV cache and overhead: roughly 50% additional (represented by 1.5 multiplier)
    base_memory_gb = (params_billions * 2) * 1.5

    # Account for max_model_len - longer sequences need more KV cache
    # Rough scaling: every 10k tokens adds ~10% memory for 7B model
    # 40000 is the baseline sequence length, 0.3 is the scaling factor
    length_factor = 1.0 + (max_model_len / 40000) * 0.3

    estimated_memory = base_memory_gb * length_factor

    # Divide by gpu_memory_utilization to get the actual free memory needed
    # (vLLM will use up to gpu_memory_utilization of available memory)
    required_free_memory = estimated_memory / gpu_memory_utilization

    logger.info(
        f"[GPU Selection] Estimated memory for {model_name}: "
        f"{estimated_memory:.2f} GB (requires {required_free_memory:.2f} GB free "
        f"with utilization={gpu_memory_utilization})"
    )

    return required_free_memory
