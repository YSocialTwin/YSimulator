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

When vLLM backend is enabled, **batch inference is automatically used** for post generation. The system:

1. **Detects vLLM backend** by checking for `generate_post_batch` method
2. **Collects post requests** during the scatter phase
3. **Processes in batch** using `generate_post_batch()` during the gather phase
4. **Falls back gracefully** to standard processing if batch metadata is unavailable

This provides significant performance improvements without requiring code changes. For Ollama (default), the standard scatter/gather pattern is used.

### How It Works

```
POST Generation Flow:
┌─────────────────────────────────────┐
│ 1. Scatter Phase                    │
│    - Generate requests for agents   │
│    - Store (agent, cluster, future, │
│      topic, day, slot, agent_attrs) │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ 2. Gather Phase                     │
│    - Detect vLLM backend            │
│    - Extract batch requests         │
│    - Call generate_post_batch()     │
│    - Process results                │
└─────────────────────────────────────┘
```

**Backward Compatibility**: Old tuple format (4 elements) is still supported and processed via standard gather.

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
│  │  - decide_reaction()               │   │
│  │  - generate_comment()              │   │
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

- `generate_post(cluster_id, day, slot, agent_attrs)`: Generate a post
- `generate_post_batch(requests)`: **New** - Batch generate posts
- `decide_reaction(cluster_id, post_content)`: Decide reaction
- `generate_comment(...)`: Generate comment
- `generate_share_commentary(...)`: Generate share commentary
- And all other LLMService methods

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

- [vLLM Documentation](https://docs.vllm.ai/)
- [Performance Optimization Roadmap](../analysis/PERFORMANCE_OPTIMIZATION_ROADMAP.md)
- [Bottleneck Analysis Summary](../analysis/BOTTLENECK_ANALYSIS_SUMMARY.md)
- [Example Configuration](../../example/llm_population_100_vllm/)

---

**Last Updated**: January 13, 2026
