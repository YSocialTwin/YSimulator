# vLLM Integration Guide

This document provides guidance for using vLLM backend in YSimulator for improved performance through batch inference.

## Overview

YSimulator now supports two LLM backends:
- **Ollama** (default): Sequential inference, macOS compatible
- **vLLM**: Batch inference with GPU acceleration, Linux only

## Quick Start

### 1. Install vLLM

```bash
pip install vllm>=0.6.0
```

**Note**: vLLM requires:
- Linux operating system (not supported on macOS)
- CUDA-compatible GPU with adequate VRAM
- Python 3.8 or higher

**Recommended for Multi-GPU Systems:**
```bash
pip install nvidia-ml-py
```
This enables GPU detection without CUDA initialization, improving GPU selection on multi-GPU systems.

### 2. Configure Backend

In your `simulation_config.json`, set the LLM backend:

```json
{
  "llm": {
    "backend": "vllm",
    "model": "meta-llama/Llama-3.2-3B",
    "temperature": 0.9,
    "max_tokens": 256,
    "tensor_parallel_size": 1,
    "gpu_memory_utilization": 0.9
  },
  "llm_v": {
    "model": "openbmb/MiniCPM-V-2_6",
    "temperature": 0.5,
    "max_tokens": 300
  }
}
```

**Note**: When using vLLM backend, both text (`llm`) and vision (`llm_v`) models are loaded within the same vLLM instance for efficient GPU memory usage.

### 3. Run Simulation

```bash
# Start server
python run_server.py --config example/llm_population_100_vllm

# Start client
python run_client.py --config example/llm_population_100_vllm
```

## Configuration Options

### vLLM Backend Configuration

#### Text Generation Model (`llm`)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `backend` | string | `"ollama"` | LLM backend: `"ollama"` or `"vllm"` |
| `model` | string | Required | Model path (HuggingFace or local) |
| `temperature` | float | `0.7` | Sampling temperature (0.0-1.0) |
| `max_tokens` | int | `256` | Maximum tokens per generation |
| `tensor_parallel_size` | int | `1` | Number of GPUs for tensor parallelism |
| `gpu_memory_utilization` | float | `0.9` | GPU memory utilization (0.0-1.0) |

#### Vision Model (`llm_v`, Optional)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `model` | string | `"openbmb/MiniCPM-V-2_6"` | Vision model path (HuggingFace or local) |
| `temperature` | float | `0.5` | Sampling temperature (0.0-1.0) |
| `max_tokens` | int | `300` | Maximum tokens per generation |

**Important**: When `backend: "vllm"` is specified, both text and vision models are loaded within the same vLLM instance, sharing GPU resources efficiently.

### Ollama Backend Configuration (Default)

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

If `backend` is omitted, Ollama is used by default for backward compatibility.

## Performance Comparison

### Baseline (Ollama Sequential)
- 100 agents, 50% LLM-based
- Round time: ~150s
- Throughput: ~0.4 rounds/min

### With vLLM (Single Actor)
- 100 agents, 50% LLM-based
- Round time: ~19s
- Throughput: ~3.2 rounds/min
- **8x speedup** (includes automatic batch inference)

### With vLLM + Load Balancing (4 Actors)
- 100 agents, 50% LLM-based
- Round time: ~5s
- Throughput: ~12 rounds/min
- **30x speedup** (batch inference + parallelization)

*Note: Performance depends on hardware, model size, and batch size.*

## Batch Inference

When vLLM backend is enabled, **batch inference is automatically used** for multiple LLM operations. The system:

1. **Detects vLLM backend** by checking for `generate_*_batch` methods
2. **Collects requests** during the scatter phase with metadata
3. **Processes in batch** using batch methods during the gather phase
4. **Falls back gracefully** to standard processing if batch metadata is unavailable

This provides 10-50x performance improvements without requiring code changes. For Ollama (default), the standard scatter/gather pattern is used.

### Batched Operations

| Operation | Batch Method | Generators | Performance Gain |
|-----------|--------------|------------|------------------|
| Posts | `generate_post_batch()` | post, cast | 8-30x |
| Comments | `generate_comment_batch()` | comment | 5-20x |
| Replies | `generate_comment_batch()` | reply | 5-20x |
| Shares | `generate_comment_batch()` | share | 5-20x |
| Reactions | `decide_reaction_batch()` | read | 5-20x (ready) |

### How It Works

```
Batch Processing Flow:
┌─────────────────────────────────────┐
│ 1. Scatter Phase                    │
│    - Generate requests for agents   │
│    - Store metadata for batching    │
│    - Create individual futures      │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ 2. Backend Detection                │
│    - Check for generate_*_batch()   │
│    - Route to batch or standard     │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ 3. Batch Processing (vLLM)          │
│    - Separate by type               │
│    - Build batch requests           │
│    - Call generate_*_batch()        │
│    - Process all results            │
│    - Apply annotations              │
│    - Calculate opinions             │
└─────────────────────────────────────┘
```

**Cascade Operations**: All dependent operations (sentiment analysis, toxicity detection, emotion extraction, opinion updates, mention marking, secondary follows) are applied AFTER batch generation, ensuring correctness.

**Backward Compatibility**: Old tuple formats are still supported and processed via standard gather.

## Architecture

### vLLM Integration

```
┌─────────────────────────────────────────────┐
│           YSimulator Client                  │
│                                             │
│  ┌────────────────────────────────────┐   │
│  │      run_client.py                  │   │
│  │  ┌──────────────────────────────┐  │   │
│  │  │  Backend Selection Logic     │  │   │
│  │  │  if backend == "vllm":       │  │   │
│  │  │    VLLMService              │  │   │
│  │  │  else:                       │  │   │
│  │  │    LLMService (Ollama)      │  │   │
│  │  └──────────────────────────────┘  │   │
│  └────────────────────────────────────┘   │
│                                             │
│  ┌────────────────────────────────────┐   │
│  │      VLLMService (Ray Actor)        │   │
│  │  ┌──────────────────────────────┐  │   │
│  │  │  vLLM Engine                 │  │   │
│  │  │  - Batch inference          │  │   │
│  │  │  - GPU acceleration         │  │   │
│  │  │  - Parallel processing      │  │   │
│  │  └──────────────────────────────┘  │   │
│  │                                    │   │
│  │  Methods:                          │   │
│  │  - generate_post()                 │   │
│  │  - generate_post_batch()          │   │
│  │  - generate_comment()              │   │
│  │  - generate_comment_batch()       │   │
│  │  - decide_reaction()               │   │
│  │  - decide_reaction_batch()        │   │
│  │  - ...                             │   │
│  └────────────────────────────────────┘   │
│                                             │
│  Optional: Load Balancer (Multiple Actors) │
│  ┌────────────────────────────────────┐   │
│  │  LLMLoadBalancer                    │   │
│  │  - Distributes requests            │   │
│  │  - Hash-based or round-robin       │   │
│  │  - Supports vllm/ollama backends   │   │
│  └────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### Batch Processing Flow

```
Agent Actions → Scatter Phase → Batch by Actor → vLLM Inference → Gather Results
                                                   (Parallel GPU)
```

## Examples

### Example 1: Basic vLLM Setup

See `example/llm_population_100_vllm/` for a complete working example.

### Example 2: Switching Backends

To switch from vLLM back to Ollama:

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

Or simply omit the `backend` field (defaults to Ollama).

### Example 3: Custom Model

```json
{
  "llm": {
    "backend": "vllm",
    "model": "mistralai/Mistral-7B-v0.1",
    "temperature": 0.7,
    "max_tokens": 512,
    "tensor_parallel_size": 2,
    "gpu_memory_utilization": 0.85
  }
}
```

## Troubleshooting

### ImportError: vLLM not installed

**Error:**
```
ImportError: vLLM is not installed. Install it with: pip install vllm
Note: vLLM requires Linux and is not supported on macOS.
```

**Solution:**
1. Install vLLM: `pip install vllm>=0.6.0`
2. Or switch to Ollama backend (remove `backend` field or set to `"ollama"`)

### CUDA Out of Memory

**Error:**
```
torch.cuda.OutOfMemoryError: CUDA out of memory
```

**Solutions:**
1. Reduce `gpu_memory_utilization` (e.g., to 0.7 or 0.5)
2. Use a smaller model (e.g., `meta-llama/Llama-3.2-1B`)
3. Reduce `max_tokens`
4. Close other GPU-using applications

### GPU Memory Allocation Error (Multi-GPU Systems)

**Error:**
```
ValueError: Free memory on device cuda:0 (3.71/39.39 GiB) on startup is less than 
desired GPU memory utilization (0.15, 5.91 GiB). Decrease GPU memory utilization 
or reduce GPU memory used by other processes.
```

**Cause:**
This error occurs on multi-GPU systems when cuda:0 doesn't have enough free memory, even though other GPUs might have sufficient memory available. vLLM defaults to using cuda:0 if not instructed otherwise.

**Automatic Solution (v1.x+):**
YSimulator now automatically handles this by:
1. **Early GPU detection (without CUDA init)**: Uses nvidia-ml-py (pynvml) to query GPU memory WITHOUT initializing CUDA
2. **Detects Ray-assigned GPUs**: Reads `CUDA_VISIBLE_DEVICES` if Ray assigned specific GPUs
3. **Dynamically selects GPU**: Chooses a GPU with sufficient free memory based on model requirements
4. **Sets environment FIRST**: Sets `CUDA_VISIBLE_DEVICES` at the very start of `__init__()` before ANY operations
5. **Then imports vLLM/PyTorch**: CUDA initializes on the correct GPU from the start
6. **Subprocess inheritance**: Environment variables properly propagate to vLLM v1 engine subprocesses (even with 'spawn')
7. **Falls back gracefully**: Warns if no GPU has sufficient memory but still attempts initialization

**Key Innovation: pynvml for GPU Detection**

Using nvidia-ml-py (pynvml) instead of torch for GPU queries:
- ✅ No CUDA initialization during GPU detection
- ✅ Can query all GPUs before setting CUDA_VISIBLE_DEVICES  
- ✅ Lightweight and fast
- ✅ Works perfectly in Docker with nvidia-container-toolkit

The GPU selection happens at the absolute beginning of VLLMService `__init__()`, before any CUDA operations, ensuring the correct GPU is used even when vLLM spawns subprocesses.

**How It Works with vLLM v1 Engine:**
vLLM v1 uses multiprocessing to spawn EngineCore subprocesses. To ensure these subprocesses use the correct GPU:
- GPU selection happens FIRST in `__init__()`, before any imports
- `CUDA_VISIBLE_DEVICES` is set using both `os.environ` and `os.putenv` for reliable subprocess inheritance
- When running as a Ray actor (the normal case), vLLM uses 'spawn' multiprocessing method (required by Ray)
- When not in Ray, multiprocessing start method is configured to 'fork' or 'forkserver' for better environment propagation
- `torch.cuda.set_device(0)` is called before vLLM initialization (after GPU remapping)
- Physical GPU 2 becomes logical device 0 within the process context

**Note on Ray Actors:**
VLLMService runs as a Ray actor (`@ray.remote`). In this context, vLLM automatically uses the 'spawn' multiprocessing method because:
- Ray actors require 'spawn' for safety and isolation
- CUDA is already initialized when the actor starts
- vLLM detects this and enforces 'spawn' internally

Despite using 'spawn', GPU selection works correctly because `os.putenv()` ensures `CUDA_VISIBLE_DEVICES` is inherited by spawned subprocesses.

**Verification:**
Check the logs for GPU selection messages:
```
[vLLM] Ray has not assigned a specific GPU, selecting based on available memory
[vLLM] Estimated memory for meta-llama/Llama-3.2-3B: 11.70 GB (requires 13.00 GB free with utilization=0.9)
[vLLM] Dynamically selected GPU 2 with 35.20 GB free (required: 13.00 GB)
[vLLM] Set CUDA_VISIBLE_DEVICES=2 before vLLM initialization
[vLLM] Current multiprocessing start method: None
[vLLM] Running in Ray actor - vLLM will use 'spawn' multiprocessing method (this is expected and required for Ray actors)
[vLLM] CUDA is available. Found 6 GPU(s)
[vLLM] Setting torch.cuda default device to 0 (physical GPU: 2)
[vLLM] Current CUDA device: 0 (NVIDIA A100-SXM4-40GB)
[vLLM] GPU memory: 35.20 GB free / 39.39 GB total
[vLLM] CUDA_VISIBLE_DEVICES: 2
[vLLM] Initializing vLLM engine with text model=meta-llama/Llama-3.2-3B...
```

Note: After setting `CUDA_VISIBLE_DEVICES=2`, the physical GPU 2 becomes logical device 0 within the process. This is normal CUDA behavior.

**GPU Selection Logging:**
GPU selection information is automatically logged to `{client_name}_llm_usage.log` for traceability. The log file is located in the `logs/` directory within your configuration folder. Example log entry:
```json
{
  "timestamp": "2026-02-10T14:50:00.000Z",
  "event": "gpu_selection",
  "backend": "vllm",
  "physical_gpu_id": 1,
  "logical_gpu_id": 0,
  "assignment_method": "dynamic_selection",
  "cuda_visible_devices": "1",
  "model": "meta-llama/Llama-3.2-3B"
}
```

This log entry appears once at initialization and helps verify which GPU was selected and how the selection was made. **Logs are written immediately** to disk (no buffering), so you can monitor them in real-time.

To view the log:
```bash
# View the log file
cat example/llm_population_100_vllm/logs/client_0_llm_usage.log

# Monitor in real-time
tail -f example/llm_population_100_vllm/logs/client_0_llm_usage.log
```

**Manual Solutions (if automatic selection fails):**
1. Reduce `gpu_memory_utilization` to fit within available memory:
   ```json
   {
     "llm": {
       "backend": "vllm",
       "gpu_memory_utilization": 0.5
     }
   }
   ```

2. Manually specify which GPU to use by setting `CUDA_VISIBLE_DEVICES`:
   ```bash
   CUDA_VISIBLE_DEVICES=1 python run_client.py --config example/llm_population_100_vllm
   ```

3. Close processes using GPU memory on cuda:0, or use a smaller model

4. If automatic selection is not working, check the logs for error messages and report the issue

### Model Download Issues

**Error:**
```
Failed to download model from HuggingFace
```

**Solution:**
1. Check internet connection
2. Verify model name/path is correct
3. Set HuggingFace token if model requires authentication:
   ```bash
   export HUGGING_FACE_HUB_TOKEN="your_token"
   ```

### macOS Not Supported

**Error:**
```
vLLM is not supported on macOS
```

**Solution:**
Use Ollama backend (default) on macOS:
```json
{
  "llm": {
    "backend": "ollama",
    "model": "llama3.2"
  }
}
```

## Best Practices

### Model Selection

1. **Small models** (1-3B params): Good for testing, lower memory
   - `meta-llama/Llama-3.2-1B`
   - `meta-llama/Llama-3.2-3B`

2. **Medium models** (7-13B params): Better quality, more memory
   - `mistralai/Mistral-7B-v0.1`
   - `meta-llama/Llama-2-13b-hf`

3. **Large models** (30B+ params): Best quality, requires multi-GPU
   - Requires `tensor_parallel_size > 1`

### Memory Management

- Start with `gpu_memory_utilization: 0.9`
- Reduce if OOM errors occur
- Monitor GPU memory with `nvidia-smi`

### Performance Optimization

1. **Use batch processing**: vLLM's strength
2. **Tune batch sizes**: Adjust based on GPU capacity
3. **Load balancing**: Use multiple actors for larger populations
4. **Model quantization**: Consider quantized models for memory

## Integration with Load Balancer

vLLM works seamlessly with the existing load balancer:

```python
from YSimulator.YClient.llm_utils.load_balancer import create_llm_actors

# Create 4 vLLM actors with load balancing
llm_actors = create_llm_actors(
    llm_config={"backend": "vllm", "model": "meta-llama/Llama-3.2-3B"},
    prompts_config=prompts_config,
    num_actors=4,
    backend="vllm",
    strategy="hash"
)
```

See [BOTTLENECK_ANALYSIS_SUMMARY.md](../analysis/BOTTLENECK_ANALYSIS_SUMMARY.md) for performance optimization details.

## API Reference

### VLLMService

Ray actor providing vLLM-based LLM inference with batch processing.

#### Methods

All methods maintain compatibility with `LLMService`:

**Standard Methods:**
- `generate_post(cluster_id, day, slot, agent_attrs)`: Generate a post
- `decide_reaction(cluster_id, post_content)`: Decide reaction
- `generate_comment(cluster_id, post_content, agent_attrs, ...)`: Generate comment
- `generate_share_commentary(cluster_id, post_content, ...)`: Generate share commentary
- And all other LLMService methods

**Batch Methods (vLLM-specific):**
- `generate_post_batch(requests)`: Batch generate posts (8-30x faster)
- `generate_comment_batch(requests)`: Batch generate comments (5-20x faster)
- `decide_reaction_batch(requests)`: Batch decide reactions (5-20x faster)

Batch methods accept a list of request dictionaries and return a list of results in the same order.

### Configuration Schema

```json
{
  "llm": {
    "backend": "vllm",           // "ollama" | "vllm"
    "model": "string",           // Required
    "temperature": 0.7,          // 0.0 - 1.0
    "max_tokens": 256,           // Integer
    "tensor_parallel_size": 1,   // Integer (GPUs)
    "gpu_memory_utilization": 0.9 // 0.0 - 1.0
  }
}
```

## Additional Resources

### Related Documentation

- **[vLLM Batch Inference](../features/VLLM_BATCH_INFERENCE.md)** - Comprehensive batch inference implementation details
- **[vLLM Integration Summary](../features/VLLM_INTEGRATION_SUMMARY.md)** - Complete implementation summary and technical design
- **[vLLM Final Report](../features/VLLM_FINAL_REPORT.md)** - Implementation report with dual-model support details
- **[Performance Optimization Roadmap](../analysis/PERFORMANCE_OPTIMIZATION_ROADMAP.md)** - System-wide performance optimization strategies
- **[Bottleneck Analysis Summary](../analysis/BOTTLENECK_ANALYSIS_SUMMARY.md)** - Quick wins and implementation guide
- **[Example Configuration](../../example/llm_population_100_vllm/)** - Working vLLM configuration example

### External Resources

- [vLLM Documentation](https://docs.vllm.ai/)
- [vLLM GitHub Repository](https://github.com/vllm-project/vllm)

## Batch Inference Implementation

YSimulator now supports comprehensive batch inference for all major LLM operations when using vLLM backend, providing 10-50x performance improvements. For detailed information about the batching implementation, see:

**[vLLM Batch Inference Documentation](../features/VLLM_BATCH_INFERENCE.md)**

### Batching Coverage

| Operation | Performance Gain | Status |
|-----------|------------------|--------|
| Posts | 5-30x | ✅ Automatic |
| Comments/Replies | 5-20x | ✅ Automatic |
| Shares | 5-20x | ✅ Automatic |
| Read Reactions | 5-20x | ✅ Automatic |
| Search Actions | 10-30x | ✅ Automatic |
| Emotion Extraction | 10-50x | ✅ Automatic |
| Opinion Evaluation | 5-20x | ✅ Automatic |

**No configuration changes needed** - batching is automatically enabled when vLLM backend is selected.

---

**Last Updated**: January 13, 2026
