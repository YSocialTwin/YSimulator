# LLM Population Example with vLLM Backend (100 Agents)

This example demonstrates YSimulator running with **vLLM backend** for efficient batch inference.

## Overview

- **Population**: 100 LLM-based agents
- **Backend**: vLLM (batch inference)
- **Text Model**: Llama-3.2-3B
- **Vision Model**: MiniCPM-V-2_6 (for image annotation)
- **Duration**: 3 days
- **Opinion Dynamics**: Disabled

## Key Features

### vLLM Backend

This example uses vLLM instead of Ollama for LLM inference, providing:

- **Parallel Processing**: Multiple vLLM actors process requests simultaneously
- **GPU Acceleration**: Efficient tensor operations on GPU
- **Higher Throughput**: Significantly faster than sequential Ollama processing
- **Unified Model Management**: Both text and vision models loaded in same vLLM instance
- **Configurable Parallelism**: Set `num_actors` to control number of parallel instances

### Performance Benefits

According to the bottleneck analysis, vLLM provides:

- **8-10x speedup** over sequential Ollama processing (single actor)
- **30x speedup** with 4 parallel actors and load balancing
- **Batch inference** reduces the LLM bottleneck from 70-80% to ~10-15% of total time
- **Scalable**: Performance scales with number of actors and GPU capacity

## Requirements

### System Requirements

- **OS**: Linux (vLLM does not support macOS)
- **GPU**: CUDA-compatible GPU with at least 8GB VRAM (for Llama-3.2-3B)
- **Python**: 3.8 or higher

### Software Requirements

```bash
pip install vllm>=0.6.0
```

**Note**: vLLM requires Linux and CUDA. For macOS users, use the Ollama backend instead (default).

## Configuration

### vLLM Configuration in `simulation_config.json`

```json
{
  "llm": {
    "backend": "vllm",
    "model": "meta-llama/Llama-3.2-3B",
    "temperature": 0.9,
    "max_tokens": 256,
    "max_model_len": 40000,
    "tensor_parallel_size": 1,
    "gpu_memory_utilization": 0.9,
    "enable_flashattention": false
  },
  "llm_v": {
    "model": "openbmb/MiniCPM-V-2_6",
    "temperature": 0.5,
    "max_tokens": 300,
    "max_model_len": 40000
  }
}
```

**Important**: When using vLLM backend, both text (`llm`) and vision (`llm_v`) models are loaded within the same vLLM instance for efficient GPU memory usage.

### Configuration Options

#### Text Generation Model (`llm`)

- `backend`: Set to `"vllm"` to use vLLM (default is `"ollama"`)
- `model`: HuggingFace model path or local model path
- `temperature`: Sampling temperature (0.0-1.0)
- `max_tokens`: Maximum tokens to generate per prompt
- `max_model_len`: Maximum sequence length for the model (default: 40000)
  - Controls the maximum context window size
  - Set based on model capabilities and memory constraints
  - Default of 40000 provides good balance for most models
- `num_actors`: Number of vLLM instances for parallel processing (default: 1)
  - **1**: Single instance, ~8-10x speedup vs Ollama
  - **2-4**: Multiple instances for higher throughput (recommended for 100+ agents)
  - Each actor requires GPU resources (~6-8GB VRAM per actor)
- `tensor_parallel_size`: Number of GPUs for tensor parallelism
- `gpu_memory_utilization`: GPU memory utilization (0.0-1.0)
- `enable_flashattention`: Enable FlashAttention 2 (default: `false`)
  - **Note**: FlashAttention 2 requires GPU compute capability >= 8.0
  - RTX 2080 Ti and older GPUs (compute capability < 8.0) should keep this `false`
  - RTX 3090, A100, H100 and newer can set this to `true` for better performance
  - When `false`, vLLM automatically selects a compatible attention backend

#### Vision Model (`llm_v`, Optional)

- `model`: Vision model path (e.g., "openbmb/MiniCPM-V-2_6")
- `temperature`: Sampling temperature (0.0-1.0)
- `max_tokens`: Maximum tokens to generate per prompt
- `max_model_len`: Maximum sequence length for the vision model (default: 40000)

## Usage

### 1. Start the Server

```bash
cd /path/to/YSimulator
python run_server.py --config example/llm_population_100_vllm
```

### 2. Start the Client

```bash
python run_client.py --config example/llm_population_100_vllm
```

## Switching Between Backends

To switch back to Ollama backend, simply change the configuration:

```json
{
  "llm": {
    "backend": "ollama",
    "address": "localhost",
    "port": 11434,
    "model": "llama3.2",
    "temperature": 0.9
  }
}
```

Or remove the `backend` field entirely (defaults to "ollama").

## Performance Comparison

### Expected Performance (100 agents, 50% LLM-based)

| Backend | Round Time | Throughput | Notes |
|---------|-----------|------------|-------|
| Ollama (sequential) | ~150s | ~0.4 rounds/min | Baseline |
| Ollama (4 actors) | ~38s | ~1.6 rounds/min | 4x speedup |
| vLLM (single actor) | ~19s | ~3.2 rounds/min | 8x speedup |
| vLLM (4 actors) | ~5s | ~12 rounds/min | 30x speedup |

**Note**: Actual performance depends on hardware, model size, and batch size.

## Troubleshooting

### Automatic GPU Selection (Multi-GPU Systems)

YSimulator automatically handles GPU selection on multi-GPU systems. When vLLM is initialized:

1. **Early Selection**: GPU selection happens BEFORE any CUDA initialization to prevent locking to cuda:0
2. **Ray Assignment**: First checks if Ray has assigned a specific GPU via `CUDA_VISIBLE_DEVICES`
3. **Memory Estimation**: Estimates required GPU memory based on model size and configuration
4. **Dynamic Selection**: Selects a GPU with sufficient free memory from all available GPUs
5. **Automatic Fallback**: Falls back gracefully with warnings if no GPU has enough memory

This prevents the common error:
```
ValueError: Free memory on device cuda:0 (3.71/39.39 GiB) on startup is less than 
desired GPU memory utilization (0.15, 5.91 GiB)
```

**What to look for in logs:**
```
[vLLM] Ray has not assigned a specific GPU, selecting based on available memory
[GPU Selection] Estimated memory for meta-llama/Llama-3.2-3B: 11.70 GB
[GPU Selection] Selected GPU 1 with 35.20 GB free (required: 13.00 GB)
[vLLM] Set CUDA_VISIBLE_DEVICES=1 before vLLM initialization
```

**GPU Selection Logging:**
GPU selection is also logged to `logs/{client_name}_llm_usage.log` for traceability:
```json
{
  "event": "gpu_selection",
  "physical_gpu_id": 1,
  "logical_gpu_id": 0,
  "assignment_method": "dynamic_selection",
  "model": "meta-llama/Llama-3.2-3B"
}
```

**Manual GPU Selection** (optional - only needed if automatic selection fails):
```bash
# Use specific GPU (e.g., GPU 1)
CUDA_VISIBLE_DEVICES=1 python run_client.py --config example/llm_population_100_vllm
```

### vLLM Not Available

If you see:
```
❌ Error: vLLM not available: vLLM is not installed.
```

**Solution**: Install vLLM with `pip install vllm>=0.6.0`

**Note**: vLLM requires Linux. On macOS, use Ollama backend instead.

### Out of Memory

If you encounter GPU OOM errors:

1. Reduce `gpu_memory_utilization` (e.g., to 0.7 or 0.5)
2. Use a smaller model (e.g., `meta-llama/Llama-3.2-1B`)
3. Reduce `max_tokens`
4. Reduce `max_model_len` (e.g., to 20000 or 10000)

### Model Not Found

If the model is not found:

1. Check model path/name is correct
2. Ensure the model is downloaded/cached
3. vLLM will automatically download from HuggingFace if needed

### FlashAttention Error

If you see:
```
ERROR: Cannot use FA version 2 is not supported due to FA2 is only supported on devices with compute capability >= 8
```

**Solution**: This is expected for older GPUs (RTX 2080 Ti, V100, etc. with compute capability < 8.0). FlashAttention is disabled by default, and vLLM will automatically register and use TORCH_SDPA backend instead. No action needed.

**To enable FlashAttention** (for newer GPUs like RTX 3090+, A100, H100):
```json
{
  "llm": {
    "enable_flashattention": true
  }
}
```

### Attention Backend Validation Error

If you see:
```
ERROR: Invalid value 'XFORMERS' for VLLM_ATTENTION_BACKEND
```

**Solution**: This has been fixed. When FlashAttention is disabled (default), vLLM now uses the TORCH_SDPA backend which is compatible with all GPU compute capabilities.

## Related Examples

- `llm_population_100_no_opinion`: Same population with Ollama backend
- `llm_population_1000`: Larger population (1000 agents) with Ollama
- `mixed_population_100`: Mixed LLM + rule-based agents

## Additional Resources

- [vLLM Documentation](https://docs.vllm.ai/)
- [Performance Optimization Roadmap](../../docs/analysis/PERFORMANCE_OPTIMIZATION_ROADMAP.md)
- [Bottleneck Analysis](../../docs/analysis/BOTTLENECK_ANALYSIS_SUMMARY.md)

---

**Last Updated**: January 10, 2026
