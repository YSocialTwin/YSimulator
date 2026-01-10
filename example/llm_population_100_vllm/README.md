# LLM Population Example with vLLM Backend (100 Agents)

This example demonstrates YSimulator running with **vLLM backend** for efficient batch inference.

## Overview

- **Population**: 100 LLM-based agents
- **Backend**: vLLM (batch inference)
- **Model**: Llama-3.2-3B
- **Duration**: 3 days
- **Opinion Dynamics**: Disabled

## Key Features

### vLLM Backend

This example uses vLLM instead of Ollama for LLM inference, providing:

- **Batch Processing**: Multiple prompts processed in parallel
- **GPU Acceleration**: Efficient tensor operations on GPU
- **Higher Throughput**: Significantly faster than sequential Ollama processing

### Performance Benefits

According to the bottleneck analysis, vLLM provides:

- **8-10x speedup** over sequential Ollama processing
- **Batch inference** reduces the LLM bottleneck from 70-80% to ~10-15% of total time
- **Scalable**: Performance scales with batch size and GPU capacity

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
    "tensor_parallel_size": 1,
    "gpu_memory_utilization": 0.9
  }
}
```

### Configuration Options

- `backend`: Set to `"vllm"` to use vLLM (default is `"ollama"`)
- `model`: HuggingFace model path or local model path
- `temperature`: Sampling temperature (0.0-1.0)
- `max_tokens`: Maximum tokens to generate per prompt
- `tensor_parallel_size`: Number of GPUs for tensor parallelism
- `gpu_memory_utilization`: GPU memory utilization (0.0-1.0)

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

### Model Not Found

If the model is not found:

1. Check model path/name is correct
2. Ensure the model is downloaded/cached
3. vLLM will automatically download from HuggingFace if needed

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
