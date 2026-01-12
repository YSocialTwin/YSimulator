# LLM Population 10000 with vLLM Backend

This example demonstrates YSimulator running a **large-scale simulation** with:
- **10,000 LLM-based agents** + **1 Fox News page**
- **vLLM backend** for efficient GPU-accelerated batch inference
- **Opinion dynamics** enabled with LLM-based evaluation (`llm_evaluation`)
- **Sentiment annotation** enabled
- **Emotion annotation** enabled

## Overview

- **Population**: 10,001 total agents (10,000 LLM agents + 1 news page)
- **Backend**: vLLM (batch inference with GPU acceleration)
- **Text Model**: Llama-3.2-3B
- **Vision Model**: MiniCPM-V-2_6 (for image annotation)
- **News Source**: Fox News RSS feed
- **Duration**: 3 days (72 rounds)
- **Opinion Dynamics**: LLM-based evaluation with natural language reasoning
- **Content Analysis**: Sentiment and emotion annotation enabled

## Key Features

### vLLM Backend for Scale

This example uses vLLM instead of Ollama, providing essential performance for large-scale simulations:

- **Parallel Processing**: Multiple vLLM actors process requests simultaneously
- **GPU Acceleration**: Efficient tensor operations on GPU
- **Configurable Actors**: Set `num_actors` in config to control parallelism
- **30x Faster**: With 4 actors compared to sequential Ollama processing
- **Memory Efficient**: Both text and vision models in same instance

**Performance Comparison** (estimated for 10,000 agents):
- Ollama sequential: ~1500-2000s per round (impractical)
- Ollama (4 actors): ~400-500s per round
- **vLLM (single actor): ~190-250s per round** (8-10x speedup)
- **vLLM (4 actors): ~50-70s per round** (30x speedup, **recommended**, default in this example)

**Configuring Number of vLLM Actors**:

The `num_actors` parameter in `simulation_config.json` controls how many vLLM instances to start:

```json
"llm": {
  "backend": "vllm",
  "num_actors": 4,
  ...
}
```

- **num_actors: 1** - Single vLLM instance, ~8-10x speedup vs Ollama
- **num_actors: 2** - Two parallel instances, ~15-20x speedup
- **num_actors: 4** - Four parallel instances, ~30x speedup (default)
- **num_actors: 8** - Eight parallel instances (requires GPU with 32GB+ VRAM)

Each actor requires GPU resources. Ensure your GPU has sufficient memory:
- **1 actor**: ~6-8GB VRAM
- **2 actors**: ~12-14GB VRAM  
- **4 actors**: ~20-24GB VRAM
- **8 actors**: ~32GB+ VRAM

**Note**: The actors share the same GPU and process requests in parallel using hash-based load balancing for agent affinity.

### Opinion Dynamics with LLM Evaluation

This example uses **LLM-based opinion evaluation** (`llm_evaluation`) which:
- Uses natural language reasoning to assess content
- Considers opinions of followed users (`evaluation_scope: neighbors`)
- Updates agent opinions based on LLM evaluation of posts
- Provides more nuanced opinion evolution than mathematical models

Opinion groups:
- **Strongly against**: 0.0 - 0.2
- **Against**: 0.2 - 0.4
- **Neutral**: 0.4 - 0.6
- **In favor**: 0.6 - 0.8
- **Strongly in favor**: 0.8 - 1.0

### Sentiment & Emotion Analysis

- **Sentiment annotation**: Analyzes positive/negative sentiment in posts
- **Emotion annotation**: Detects emotions (joy, anger, sadness, fear, etc.)
- Both are LLM-powered and run during content generation

### News Page

- **Fox News RSS feed**: Single news page aggregating from Fox News
- **LLM-enabled**: Uses LLM to generate commentary on news articles
- **Right-leaning**: `leaning: "right"` in agent configuration
- **Always active**: Posts news throughout simulation

## Requirements

### Hardware Requirements

- **OS**: Linux (vLLM does not support macOS)
- **GPU**: CUDA-compatible GPU with **at least 16GB VRAM recommended** for 10K agents
  - Minimum: 8GB VRAM (may need to reduce batch sizes)
  - Recommended: 16GB+ VRAM (RTX 4090, A100, etc.)
- **RAM**: 16GB+ system RAM recommended
- **Storage**: 10GB+ for models and simulation data

### Software Requirements

```bash
pip install vllm>=0.6.0
```

**Note**: vLLM requires Linux and CUDA. For macOS, this example will not work - use Ollama-based examples instead.

## Quick Start

### 1. Generate Population and Network

```bash
cd example/llm_population_10000_vllm
python generate_population.py
```

This creates:
- `agent_population.json` - 10,001 agent definitions
- `network.csv` - Initial social network (~100,000 edges)

### 2. Start Server

```bash
# From repository root
python run_server.py --config example/llm_population_10000_vllm
```

### 3. Start Client

```bash
# In a separate terminal
python run_client.py --config example/llm_population_10000_vllm
```

## Configuration

### vLLM Settings

```json
{
  "llm": {
    "backend": "vllm",
    "model": "meta-llama/Llama-3.2-3B",
    "max_model_len": 40000,
    "tensor_parallel_size": 1,
    "gpu_memory_utilization": 0.9,
    "enable_flashattention": false
  }
}
```

**Key parameters**:
- `max_model_len`: Maximum context length (40,000 tokens)
- `gpu_memory_utilization`: GPU memory usage (0.9 = 90%)
- `enable_flashattention`: Disabled by default (requires compute capability >= 8.0)

### Opinion Dynamics Settings

```json
{
  "opinion_dynamics": {
    "enabled": true,
    "model_name": "llm_evaluation",
    "parameters": {
      "evaluation_scope": "neighbors",
      "cold_start": "neutral"
    }
  }
}
```

**Parameters**:
- `evaluation_scope`: `"neighbors"` considers followed users' opinions
- `cold_start`: `"neutral"` initializes new opinions at 0.5

### Content Analysis Settings

```json
{
  "simulation": {
    "enable_sentiment": true,
    "emotion_annotation": true
  }
}
```

## Performance Optimization

### For Large Populations

1. **Use vLLM with multiple actors** (load balancing):
   - Edit `run_client.py` to use load balancer with 4+ actors
   - Provides 30x speedup over sequential processing

2. **Adjust batch size**:
   ```json
   {
     "agents": {
       "batch_size": 100
     }
   }
   ```
   - Larger batches = better GPU utilization
   - May need to reduce if hitting memory limits

3. **Reduce GPU memory if OOM**:
   ```json
   {
     "llm": {
       "gpu_memory_utilization": 0.7,
       "max_model_len": 20000
     }
   }
   ```

4. **Use PostgreSQL instead of SQLite**:
   - Better performance for large simulations
   - Edit `server_config.json` to use PostgreSQL

### Expected Performance

With recommended hardware (16GB+ VRAM GPU):
- **Round time**: 50-70 seconds per round (with 4 vLLM actors)
- **Total simulation**: ~60-90 minutes for 72 rounds (3 days)
- **Memory usage**: ~8-10GB GPU VRAM, ~8-12GB system RAM
- **Database size**: Grows with simulation (expect 5-10GB for full run)

## File Structure

```
llm_population_10000_vllm/
├── README.md                    # This file
├── generate_population.py       # Generate agents and network
├── agent_population.json        # Generated: 10,001 agent definitions
├── network.csv                  # Generated: Social network (~100K edges)
├── simulation_config.json       # Client configuration
├── server_config.json           # Server configuration
└── prompts.json                 # LLM prompts for agent behaviors
```

## Monitoring

### Logs

- **Server logs**: `ysimulator.log` - Server events and network operations
- **Client logs**: Check console output for round progress
- **LLM usage**: Enabled by default to track API calls

### Database

- **SQLite database**: `simulation.db`
- Query to monitor progress:
  ```sql
  SELECT COUNT(*) FROM posts;
  SELECT COUNT(*) FROM comments;
  SELECT round, COUNT(*) FROM posts GROUP BY round;
  ```

## Troubleshooting

### Out of Memory (GPU)

**Symptoms**: "CUDA out of memory" errors

**Solutions**:
1. Reduce `gpu_memory_utilization` to 0.7 or 0.5
2. Reduce `max_model_len` to 20000 or 10000
3. Reduce batch size to 50 or 25
4. Use a smaller model (e.g., `meta-llama/Llama-3.2-1B`)

### Slow Performance

**Symptoms**: Rounds taking >5 minutes each

**Solutions**:
1. Ensure vLLM is installed and being used (check logs for "[vLLM]")
2. Verify GPU is being used (check `nvidia-smi`)
3. Increase batch size for better GPU utilization
4. Use load balancer with multiple actors (4-8 recommended)

### Network Loading Timeout

**Symptoms**: "Timeout loading network" error

**Solutions**:
1. Increase `timeout_seconds` in `server_config.json` (e.g., to 300)
2. Network with 100K edges takes ~100-150 seconds to load
3. This is normal for large networks

### Opinion Dynamics Not Working

**Symptoms**: Opinions not updating

**Verification**:
1. Check `opinion_dynamics.enabled` is `true` in `simulation_config.json`
2. Verify `model_name` is `"llm_evaluation"`
3. Ensure agents are LLM-enabled (`llm: true`)
4. Check logs for opinion evaluation messages

### FlashAttention Warning

**Symptoms**: `"Cannot use FA version 2"` error

**Solution**: This is expected and normal. FlashAttention is disabled by default (`enable_flashattention: false`), and vLLM automatically uses TORCH_SDPA backend instead. No action needed.

**To enable FlashAttention** (only for GPUs with compute capability >= 8.0):
```json
{
  "llm": {
    "enable_flashattention": true
  }
}
```

## Customization

### Change News Source

Edit `generate_population.py` line 24:
```python
"feed_url": "https://your-news-source.com/rss",
```

### Adjust Agent Distribution

Edit `generate_population.py`:
- Change `leanings` distribution (line 51)
- Modify `archetypes` ratio (line 48)
- Adjust interest topics (line 67)

### Modify Opinion Groups

Edit `simulation_config.json` `opinion_dynamics.opinion_groups`:
```json
{
  "opinion_groups": {
    "Custom Group 1": [0.0, 0.33],
    "Custom Group 2": [0.33, 0.66],
    "Custom Group 3": [0.66, 1.0]
  }
}
```

### Change Simulation Duration

Edit `simulation_config.json`:
```json
{
  "simulation": {
    "num_days": 7,
    "num_slots_per_day": 24
  }
}
```

## Related Examples

- `llm_population_100_vllm`: Smaller 100-agent version for testing
- `llm_population_100_llm_opinion`: 100 agents with Ollama backend
- `llm_population_10000`: 10K agents with Ollama (much slower)

## Additional Resources

- [vLLM Documentation](https://docs.vllm.ai/)
- [vLLM Integration Guide](../../docs/configuration/VLLM_INTEGRATION_GUIDE.md)
- [Performance Analysis](../../docs/analysis/BOTTLENECK_ANALYSIS_SUMMARY.md)
- [YSimulator Documentation](../../docs/)

---

**Created**: January 12, 2026
**vLLM Integration**: Production Ready
**Recommended For**: Large-scale opinion dynamics research
