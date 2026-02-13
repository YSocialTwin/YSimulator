"""
GPU utility functions for vLLM service.

This module provides utilities for GPU memory checking and device selection
to support dynamic GPU allocation on multi-GPU systems.

Uses nvidia-ml-py (pynvml) for GPU queries to avoid CUDA initialization.
"""

import logging
import os
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Constants for memory estimation
BASELINE_SEQUENCE_LENGTH = 40000  # Standard sequence length for memory calculation
SEQUENCE_SCALING_FACTOR = 0.3  # Memory scaling factor per additional sequence length
KV_CACHE_OVERHEAD_MULTIPLIER = 1.5  # Overhead multiplier for KV cache (50% additional)


def _get_gpu_device_name(device_id: int) -> str:
    """
    Get the device name for a specific GPU.

    Args:
        device_id: CUDA device ID to query

    Returns:
        GPU device name (e.g., 'NVIDIA A100-SXM4-40GB') or 'Unknown GPU' if unavailable
    """
    try:
        import pynvml

        pynvml.nvmlInit()
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(device_id)
            name = pynvml.nvmlDeviceGetName(handle)
            # Handle both bytes and str return types
            if isinstance(name, bytes):
                return name.decode("utf-8")
            return name
        finally:
            try:
                pynvml.nvmlShutdown()
            except:
                pass
    except:
        return "Unknown GPU"


def get_gpu_memory_info(device_id: int = 0) -> Tuple[float, float]:
    """
    Get memory information for a specific GPU device.

    Uses pynvml (nvidia-ml-py) to query GPU without initializing CUDA.
    This is critical for early GPU selection before CUDA context creation.

    Args:
        device_id: CUDA device ID to query

    Returns:
        Tuple of (free_memory_gb, total_memory_gb)

    Raises:
        RuntimeError: If unable to query GPU memory
    """
    try:
        # Try pynvml first (preferred - no CUDA initialization)
        import pynvml

        pynvml.nvmlInit()
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(device_id)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)

            free_gb = info.free / (1024**3)
            total_gb = info.total / (1024**3)

            return free_gb, total_gb
        finally:
            try:
                pynvml.nvmlShutdown()
            except:
                pass

    except (ImportError, Exception) as e:
        logger.debug(f"pynvml not available or failed ({e}), falling back to torch")

        # Fallback to torch (initializes CUDA - not ideal for early detection)
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
            raise RuntimeError("Neither pynvml nor PyTorch is available. Cannot query GPU memory.")
        except Exception as e:
            raise RuntimeError(f"Failed to query GPU memory: {e}")


def _get_physical_gpu_count_and_unmask() -> Tuple[int, Optional[str]]:
    """
    Get the actual number of physical GPUs on the host and temporarily unmask all.

    Ray assigns GPUs by setting CUDA_VISIBLE_DEVICES, which masks other GPUs.
    This function temporarily unmasks ALL physical GPUs to enable complete discovery.

    Returns:
        Tuple of (physical_gpu_count, original_cuda_visible_devices)

    Raises:
        RuntimeError: If unable to query physical GPU count
    """
    try:
        import pynvml

        # Save Ray's CUDA_VISIBLE_DEVICES assignment (if any)
        original_cuda_visible_devices = os.environ.get("CUDA_VISIBLE_DEVICES")

        logger.info(
            f"[GPU Query] Original CUDA_VISIBLE_DEVICES from Ray: {original_cuda_visible_devices}"
        )

        # Initialize NVML to talk to NVIDIA drivers
        pynvml.nvmlInit()
        try:
            # Get the actual number of physical GPUs on this host (not masked count)
            device_count = pynvml.nvmlDeviceGetCount()
            logger.info(f"[GPU Query] Physical GPU count on host: {device_count}")

            # Create a portable visibility string for all physical GPUs (e.g., "0,1,2,3,4,5")
            all_gpu_ids = ",".join([str(i) for i in range(device_count)])

            # Temporarily unmask ALL physical GPUs to perform memory check
            logger.info(f"[GPU Query] Temporarily unmasking all GPUs: {all_gpu_ids}")
            os.environ["CUDA_VISIBLE_DEVICES"] = all_gpu_ids
            os.putenv("CUDA_VISIBLE_DEVICES", all_gpu_ids)

            return device_count, original_cuda_visible_devices
        finally:
            try:
                pynvml.nvmlShutdown()
            except:
                pass

    except Exception as e:
        logger.warning(
            f"[GPU Query] Failed to unmask GPUs: {e}. Using current CUDA_VISIBLE_DEVICES."
        )
        # If unmasking fails, return current device count (masked view)
        try:
            import pynvml

            pynvml.nvmlInit()
            try:
                device_count = pynvml.nvmlDeviceGetCount()
                return device_count, os.environ.get("CUDA_VISIBLE_DEVICES")
            finally:
                try:
                    pynvml.nvmlShutdown()
                except:
                    pass
        except:
            # Last resort - use torch
            try:
                import torch

                return torch.cuda.device_count(), os.environ.get("CUDA_VISIBLE_DEVICES")
            except:
                raise RuntimeError("Unable to query GPU count")


def get_all_gpu_memory_info() -> List[Tuple[int, float, float]]:
    """
    Get memory information for all available GPUs.

    Uses pynvml (nvidia-ml-py) to query GPUs without initializing CUDA.
    Temporarily unmasks Ray-hidden GPUs to discover all physical GPUs on the host.

    Returns:
        List of tuples (device_id, free_memory_gb, total_memory_gb)

    Raises:
        RuntimeError: If unable to query GPU memory
    """
    original_cuda_visible_devices = None

    try:
        # Try pynvml first (preferred - no CUDA initialization)
        import pynvml

        # Unmask all GPUs to see the complete picture
        device_count, original_cuda_visible_devices = _get_physical_gpu_count_and_unmask()

        logger.info(f"[GPU Query] Querying all {device_count} physical GPU(s)...")

        gpu_info = []
        for device_id in range(device_count):
            free_gb, total_gb = get_gpu_memory_info(device_id)
            gpu_name = _get_gpu_device_name(device_id)
            gpu_info.append((device_id, free_gb, total_gb))

            # Log detailed information for each GPU
            logger.info(
                f"[GPU Query]   GPU {device_id}: {gpu_name} - "
                f"{free_gb:.2f} GB free / {total_gb:.2f} GB total"
            )

        logger.info(f"[GPU Query] Found {len(gpu_info)} physical GPU(s) on host")

        return gpu_info

    except (ImportError, Exception) as e:
        logger.debug(f"pynvml not available or failed ({e}), falling back to torch")

        # Fallback to torch
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
            raise RuntimeError("Neither pynvml nor PyTorch is available. Cannot query GPU memory.")

    finally:
        # Restore original CUDA_VISIBLE_DEVICES (Ray's assignment)
        if original_cuda_visible_devices is not None:
            logger.info(
                f"[GPU Query] Restored original CUDA_VISIBLE_DEVICES: {original_cuda_visible_devices}"
            )
            os.environ["CUDA_VISIBLE_DEVICES"] = original_cuda_visible_devices
            os.putenv("CUDA_VISIBLE_DEVICES", original_cuda_visible_devices)
        elif "CUDA_VISIBLE_DEVICES" in os.environ and original_cuda_visible_devices is None:
            # Original was None but we set it, so remove it
            logger.info("[GPU Query] Removing temporary CUDA_VISIBLE_DEVICES")
            del os.environ["CUDA_VISIBLE_DEVICES"]


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


def get_ordered_gpus_by_memory(
    required_memory_gb: Optional[float] = None,
) -> List[Tuple[int, float, float]]:
    """
    Get list of GPUs ordered by free memory (descending).

    Args:
        required_memory_gb: Optional minimum required free memory in GB.
                          If specified, only GPUs with sufficient memory are returned.

    Returns:
        List of tuples: (device_id, free_gb, total_gb) sorted by free_gb descending
        Returns empty list if no suitable GPUs found.

    Example:
        >>> gpus = get_ordered_gpus_by_memory(required_memory_gb=10.0)
        >>> # [(2, 35.2, 40.0), (1, 28.3, 40.0), (0, 15.1, 40.0)]
    """
    try:
        gpu_info = get_all_gpu_memory_info()

        if not gpu_info:
            logger.warning("[GPU Selection] No GPUs available")
            return []

        logger.info(f"[GPU Selection] Found {len(gpu_info)} GPU(s) before filtering")

        # Filter by required memory if specified
        if required_memory_gb is not None:
            logger.info(
                f"[GPU Selection] Filtering GPUs with >= {required_memory_gb:.2f} GB free memory"
            )

            # Keep original list for logging
            original_gpu_info = list(gpu_info)
            gpu_info = []

            for device_id, free_gb, total_gb in original_gpu_info:
                if free_gb >= required_memory_gb:
                    gpu_info.append((device_id, free_gb, total_gb))
                    logger.info(f"[GPU Selection]   GPU {device_id}: {free_gb:.2f} GB free ✅")
                else:
                    logger.info(
                        f"[GPU Selection]   GPU {device_id}: {free_gb:.2f} GB free ❌ (insufficient)"
                    )

            if not gpu_info:
                logger.warning(
                    f"[GPU Selection] No GPU found with {required_memory_gb:.2f} GB free memory"
                )
                return []

            logger.info(f"[GPU Selection] Found {len(gpu_info)} candidate GPU(s) after filtering")

        # Sort by free memory (descending)
        gpu_info.sort(key=lambda x: x[1], reverse=True)

        # Log final candidate list
        logger.info("[GPU Selection] Candidate GPUs (sorted by free memory):")
        for idx, (device_id, free_gb, total_gb) in enumerate(gpu_info, 1):
            logger.info(f"[GPU Selection]   {idx}. GPU {device_id}: {free_gb:.2f} GB free")

        return gpu_info

    except Exception as e:
        logger.error(f"[GPU Selection] Failed to get GPU list: {e}")
        return []


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


def get_total_gpu_count() -> int:
    """
    Get the total number of physical GPUs available on the system.

    This function queries the actual hardware, not just what's visible via CUDA_VISIBLE_DEVICES.

    Returns:
        Total number of physical GPUs available

    Raises:
        RuntimeError: If unable to query GPU count
    """
    try:
        import pynvml

        pynvml.nvmlInit()
        try:
            device_count = pynvml.nvmlDeviceGetCount()
            logger.info(f"[GPU Query] Total physical GPUs on system: {device_count}")
            return device_count
        finally:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass

    except (ImportError, Exception) as e:
        logger.debug(f"pynvml not available or failed ({e}), falling back to torch")

        # Fallback to torch
        try:
            import torch

            if not torch.cuda.is_available():
                logger.warning("[GPU Query] CUDA is not available")
                return 0

            device_count = torch.cuda.device_count()
            logger.info(f"[GPU Query] Total GPUs visible to torch: {device_count}")
            return device_count
        except ImportError:
            raise RuntimeError("Neither pynvml nor PyTorch is available. Cannot query GPU count.")
        except Exception as e:
            raise RuntimeError(f"Failed to query GPU count: {e}")


def estimate_required_vllm_memory(
    model_name: str,
    max_model_len: int = 40000,
    gpu_memory_utilization: float = 0.9,
) -> float:
    """
    Estimate the required GPU memory for loading a vLLM model.

    This is a rough estimate based on model size. Actual memory usage may vary.
    Supports quantized models (int4, int8, awq, gptq) and vision models.

    Args:
        model_name: Name of the model (e.g., "meta-llama/Llama-3.2-3B", "openbmb/MiniCPM-V-2_6-int4")
        max_model_len: Maximum sequence length
        gpu_memory_utilization: Target GPU memory utilization

    Returns:
        Estimated required memory in GB
    """
    # Extract parameter count from model name if possible
    # This is a heuristic and may not work for all model names
    model_name_lower = model_name.lower()
    
    # Detect quantization format and set bytes per parameter
    bytes_per_param = 2.0  # Default: FP16
    quantization_type = "FP16"
    
    if "int4" in model_name_lower or "4bit" in model_name_lower:
        bytes_per_param = 0.5
        quantization_type = "int4"
    elif "int8" in model_name_lower or "8bit" in model_name_lower:
        bytes_per_param = 1.0
        quantization_type = "int8"
    elif "awq" in model_name_lower or "gptq" in model_name_lower:
        bytes_per_param = 0.5  # 4-bit quantization
        quantization_type = "AWQ/GPTQ"
    elif "gguf" in model_name_lower:
        # GGUF can be various quantizations, assume 4-bit for safety
        bytes_per_param = 0.5
        quantization_type = "GGUF"

    # Common model size patterns
    # Check for vision models first (MiniCPM-V-2_6, etc.)
    if "minicpm-v" in model_name_lower:
        # MiniCPM-V-2_6 is a 2.6B parameter model
        if "2_6" in model_name_lower or "2.6" in model_name_lower:
            params_billions = 2.6
        elif "8b" in model_name_lower:
            params_billions = 8
        else:
            params_billions = 2.6  # Default for MiniCPM-V
    elif "llava" in model_name_lower:
        # LLaVA models - check for size in name
        if "7b" in model_name_lower:
            params_billions = 7
        elif "13b" in model_name_lower:
            params_billions = 13
        elif "34b" in model_name_lower:
            params_billions = 34
        else:
            params_billions = 7  # Default LLaVA
    elif "1b" in model_name_lower or "1.5b" in model_name_lower:
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

    # Model weights: params * bytes_per_param
    # KV cache and overhead: roughly 50% additional (represented by multiplier)
    base_memory_gb = (params_billions * bytes_per_param) * KV_CACHE_OVERHEAD_MULTIPLIER

    # Account for max_model_len - longer sequences need more KV cache
    # Rough scaling: every 10k tokens adds ~10% memory for 7B model
    # Uses baseline sequence length and scaling factor as constants
    length_factor = 1.0 + (max_model_len / BASELINE_SEQUENCE_LENGTH) * SEQUENCE_SCALING_FACTOR

    estimated_memory = base_memory_gb * length_factor

    # Divide by gpu_memory_utilization to get the actual free memory needed
    # (vLLM will use up to gpu_memory_utilization of available memory)
    required_free_memory = estimated_memory / gpu_memory_utilization

    logger.info(
        f"[GPU Selection] Estimated memory for {model_name}: "
        f"{estimated_memory:.2f} GB ({params_billions}B params, {quantization_type}, "
        f"{bytes_per_param} bytes/param) "
        f"(requires {required_free_memory:.2f} GB free with utilization={gpu_memory_utilization})"
    )

    return required_free_memory


def select_dedicated_gpu_for_vision(
    required_memory_gb: Optional[float] = None, exclude_gpus: Optional[List[int]] = None
) -> Optional[int]:
    """
    Select a dedicated GPU for vision LLM, excluding GPUs already in use.

    This function is used to allocate a separate GPU for image transcription/vision
    tasks in multi-GPU environments to avoid memory contention.

    Args:
        required_memory_gb: Optional minimum required free memory in GB
        exclude_gpus: Optional list of GPU IDs to exclude (e.g., ones already in use)

    Returns:
        GPU device ID suitable for vision LLM, or None if no suitable GPU found

    Example:
        >>> # Select a GPU for vision, excluding GPU 0 (used for text generation)
        >>> vision_gpu = select_dedicated_gpu_for_vision(
        ...     required_memory_gb=8.0,
        ...     exclude_gpus=[0]
        ... )
    """
    if exclude_gpus is None:
        exclude_gpus = []

    try:
        # Get all GPUs sorted by free memory
        gpu_info = get_ordered_gpus_by_memory(required_memory_gb=required_memory_gb)

        if not gpu_info:
            logger.warning(
                "[GPU Selection] No GPUs with sufficient memory found for vision LLM"
            )
            return None

        # Filter out excluded GPUs
        available_gpus = [
            (device_id, free_gb, total_gb)
            for device_id, free_gb, total_gb in gpu_info
            if device_id not in exclude_gpus
        ]

        if not available_gpus:
            logger.warning(
                f"[GPU Selection] No available GPUs after excluding {exclude_gpus}"
            )
            return None

        # Select the GPU with the most free memory (first in sorted list)
        selected_gpu_id = available_gpus[0][0]
        selected_free_gb = available_gpus[0][1]

        logger.info(
            f"[GPU Selection] Selected GPU {selected_gpu_id} for vision LLM "
            f"({selected_free_gb:.2f} GB free, excluding GPUs: {exclude_gpus})"
        )

        return selected_gpu_id

    except Exception as e:
        logger.error(f"[GPU Selection] Failed to select dedicated GPU for vision: {e}")
        return None
