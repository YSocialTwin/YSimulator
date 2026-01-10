# Bottleneck Analysis Summary

**Quick Reference Guide for YSimulator Performance Optimization**

**Date**: January 10, 2026  
**Status**: Active  
**Related**: [Performance Optimization Roadmap](./PERFORMANCE_OPTIMIZATION_ROADMAP.md)

---

## TL;DR - Critical Findings

🔴 **Primary Bottleneck**: Sequential LLM inference (70-80% of execution time)  
🟡 **Secondary**: Synchronous database queries (10-15%)  
✅ **Already Optimized**: Database batching (97% improvement), Redis caching (85-90%)  
🎯 **Quick Win**: Add 4 LLM actors → **4x speedup in 2 days**  
🚀 **Ultimate Goal**: **30x+ overall speedup** achievable through 3-phase optimization

---

## Bottleneck Quick Reference

| ID | Bottleneck | Time % | Impact | Quick Fix | Full Fix |
|----|------------|--------|--------|-----------|----------|
| **B1** | Sequential LLM Inference | 70-80% | 🔴 Critical | 4 LLM actors (4x) | vLLM batch (10x) |
| **B2** | Sync DB Queries | 10-15% | 🟡 Moderate | Pre-fetch data (2x) | Async context (3x) |
| **B3** | Recommendation Queries | 5-10% | 🟡 Moderate | Redis cache (2x) | Pre-computed (5x) |
| B4 | Barrier Sync | 2-5% | 🟢 Low | N/A | Overlapping (1.5x) |
| B5 | Agent Scheduling | 1-2% | 🟢 Low | N/A | Optimize filters |
| B6 | Text Annotation | 0-10% | 🟢 Low | Disable if unused | Batch API calls |

---

## Current System Performance (Baseline)

### Test Configuration
```
- Agents: 1,000
- LLM-based: 50%
- Rule-based: 50%
- Actions per round: 10
- LLM latency: ~300ms average
```

### Performance Profile
```
Round Time: 10,000ms (10 seconds)

Breakdown:
├─ Agent Scheduling:      5ms    (1%)
├─ Scatter Phase:         50ms   (5%)
├─ LLM Gather Phase:      9000ms (90%)  ← BOTTLENECK
└─ Database Operations:   400ms  (4%)
```

### Scalability Limits
- **Current**: 1,000 agents → ~10s per round → ~6 rounds/minute
- **Daily capacity**: 8,640 rounds (24 hours)
- **Bottleneck**: LLM inference can't scale beyond single-actor processing

---

## Why LLM is the Bottleneck

### Current LLM Flow

```python
# SCATTER PHASE (parallel dispatch) ✅
futures = []
for agent in active_agents:
    future = llm.generate_post.remote(...)
    futures.append(future)
    # Non-blocking, returns immediately

# GATHER PHASE (sequential processing) ⚠️
results = ray.get(futures)
# Blocks until ALL futures complete
# But LLM processes them ONE BY ONE!
```

### Sequential Processing Issue

```
Time ────────────────────────────────────────────────>

LLM Actor:
├─ Process Request 1 (300ms)
├─ Process Request 2 (300ms)
├─ Process Request 3 (300ms)
├─ ...
└─ Process Request 500 (300ms)

Total Time: 500 requests × 300ms = 150,000ms (2.5 minutes!)
```

### Why This Happens

1. **Single LLM Actor**: Only one Ray actor handles all requests
2. **Ollama Sequential**: Ollama processes one request at a time
3. **No Batching**: Each request is independent (no batch inference)
4. **Model Capacity**: Single GPU/CPU can only serve one request at a time

---

## Optimization Strategy Quick Reference

### Phase 1: Quick Wins (1-2 weeks) → **4x Speedup**

#### 1. Multiple LLM Actors (2 days)
```python
# Current: 1 actor
llm = LLMService.remote(config)

# Optimized: 4 actors
NUM_ACTORS = 4
llm_actors = [LLMService.remote(config) for _ in range(NUM_ACTORS)]

def get_llm_actor(agent_id):
    idx = hash(agent_id) % NUM_ACTORS
    return llm_actors[idx]

# Use in scatter phase
for agent in active_agents:
    llm = get_llm_actor(agent.id)
    future = llm.generate_post.remote(...)
```

**Expected Result**: 500 requests / 4 actors = 125 requests per actor × 300ms = 37,500ms (37s)
→ **4x speedup** (from 150s to 37s)

#### 2. Database Pre-fetching (3 days)
```python
# Current: Per-agent queries
for agent in active_agents:
    post = ray.get(server.get_post.remote(post_id))  # 10ms × N agents
    followers = ray.get(server.get_followers.remote(agent_id))  # 10ms × N agents

# Optimized: Batch queries
recent_posts = ray.get(server.get_posts_batch.remote(post_ids))
all_followers = ray.get(server.get_followers_batch.remote(agent_ids))

for agent in active_agents:
    # Use pre-fetched data (0ms)
    post = recent_posts[post_id]
    followers = all_followers[agent.id]
```

**Expected Result**: 50ms → 15ms in scatter phase → **3x speedup**

#### 3. Recommendation Caching (2 days)
```python
# Add Redis cache for recommendations
cache_key = f"recsys:{agent_id}:{mode}:{limit}"
cached = redis.get(cache_key)

if cached:
    return json.loads(cached)  # Instant (1ms)
else:
    recommendations = compute_recommendations(...)  # Expensive (20ms)
    redis.setex(cache_key, ttl=300, value=json.dumps(recommendations))
    return recommendations
```

**Expected Result**: 20ms → 5ms average (75% cache hit rate) → **4x speedup** for recommendations

### Phase 2: Advanced (2-4 weeks) → **16x Cumulative Speedup**

#### 4. vLLM Integration (5 days)
```python
from vllm import LLM, SamplingParams

class VLLMService:
    def __init__(self):
        self.llm = LLM(model="llama3.2", tensor_parallel_size=1)
        self.sampling_params = SamplingParams(temperature=0.7)
    
    def generate_batch(self, prompts):
        """Process ALL prompts in parallel with batch inference."""
        return self.llm.generate(prompts, self.sampling_params)

# Usage
prompts = [build_prompt(agent) for agent in active_agents]
results = vllm_service.generate_batch(prompts)  # Parallel inference!
```

**Expected Result**: 
- 500 requests with batch size 32 → 16 batches
- 16 batches × 1,200ms per batch = 19,200ms (19s)
- **With 4 actors**: 19s / 4 = 4.8s
- **8x speedup** over Phase 1 (37s → 4.8s)

### Phase 3: Advanced Features (4-6 weeks) → **30x+ Cumulative Speedup**

See [full roadmap](./PERFORMANCE_OPTIMIZATION_ROADMAP.md#phase-3-advanced-features-4-6-weeks) for details.

---

## Performance Gains Summary

| Phase | Optimizations | Round Time | Speedup vs Baseline | Implementation |
|-------|---------------|------------|---------------------|----------------|
| Baseline | None | 10.0s | 1.0x | Current |
| Phase 1 | 4 LLM actors + DB prefetch + RecSys cache | 2.6s | 3.8x | 1-2 weeks |
| Phase 2 | + vLLM + LLM cache + Precomputed feeds | 0.6s | 16.3x | +2-4 weeks |
| Phase 3 | + Hybrid actors + Semantic cache + Overlap | 0.3s | 31.7x | +4-6 weeks |

---

## Quick Implementation Guide

### Step 1: Verify Current Performance (30 min)

```bash
# Run baseline benchmark
python scripts/benchmark_simulation.py \
    --config example/llm_population_1000 \
    --rounds 10 \
    --output baseline_results.json

# View results
cat baseline_results.json | jq '.avg_round_time_ms'
```

### Step 2: Implement Multiple LLM Actors (2 days)

**File**: `YSimulator/YClient/client.py`

```python
# Add to __init__
NUM_LLM_ACTORS = self.simulation_config.get('llm', {}).get('num_actors', 1)
self.llm_actors = []

if NUM_LLM_ACTORS > 1:
    # Create multiple actors
    for i in range(NUM_LLM_ACTORS):
        actor = LLMService.remote(
            llm_config=llm_config,
            prompts_config=prompts_config
        )
        self.llm_actors.append(actor)
    
    # Load balancer
    self.llm_load_balancer = LoadBalancer(self.llm_actors)
else:
    # Single actor (backwards compatible)
    self.llm_actors = [llm_handle]
    self.llm_load_balancer = None

# Update action generators to use load balancer
def get_llm_for_agent(self, agent_id):
    if self.llm_load_balancer:
        return self.llm_load_balancer.get_actor(agent_id)
    return self.llm_actors[0]
```

**Configuration**: `simulation_config.json`

```json
{
  "llm": {
    "num_actors": 4,
    "load_balancing": "hash"
  }
}
```

### Step 3: Test and Validate (1 day)

```bash
# Run benchmark with optimization
python scripts/benchmark_simulation.py \
    --config example/llm_population_1000_optimized \
    --rounds 10 \
    --output phase1_results.json

# Compare results
python scripts/compare_benchmarks.py \
    baseline_results.json \
    phase1_results.json
```

Expected output:
```
Baseline:    10.2s per round
Phase 1:     2.7s per round
Speedup:     3.8x
Status:      ✅ Target achieved (expected 3.8x)
```

---

## Monitoring Checklist

After implementing optimizations, monitor:

- [ ] Round execution time (should decrease)
- [ ] LLM throughput (calls per second - should increase)
- [ ] LLM actor utilization (should be balanced across actors)
- [ ] Cache hit rates (recommendations, LLM responses)
- [ ] Database query counts (should decrease with pre-fetching)
- [ ] Memory usage (may increase with multiple actors)
- [ ] CPU/GPU utilization (should increase)
- [ ] Output quality (A/B test vs baseline)

---

## Common Issues & Solutions

### Issue 1: Memory Overflow with Multiple Actors

**Symptom**: Out of memory errors with 4+ LLM actors

**Solution**:
```python
# Reduce model memory footprint
llm_config = {
    "model": "llama3.2",
    "quantization": "int8",  # Use 8-bit quantization
    "max_model_len": 1024,   # Reduce context window
}

# Or use fewer actors
NUM_LLM_ACTORS = 2  # Instead of 4
```

### Issue 2: Unbalanced Load Across Actors

**Symptom**: Some actors idle while others busy

**Solution**:
```python
# Use round-robin instead of hash-based
class LoadBalancer:
    def __init__(self, actors):
        self.actors = actors
        self.current_idx = 0
    
    def get_actor(self, agent_id=None):
        actor = self.actors[self.current_idx]
        self.current_idx = (self.current_idx + 1) % len(self.actors)
        return actor
```

### Issue 3: Cache Staleness Affects Quality

**Symptom**: Repeated content, outdated recommendations

**Solution**:
```python
# Reduce cache TTL
RECOMMENDATION_CACHE_TTL = 60  # 1 minute instead of 5

# Or disable caching for specific operations
CACHE_CONFIG = {
    "generate_post": False,      # Always fresh
    "decide_follow": True,        # Cacheable (deterministic)
    "extract_topics": True,       # Cacheable (stable)
    "get_recommendations": True,  # Cacheable (with TTL)
}
```

---

## Next Steps

1. **Read Full Roadmap**: [PERFORMANCE_OPTIMIZATION_ROADMAP.md](./PERFORMANCE_OPTIMIZATION_ROADMAP.md)
2. **Implement Phase 1**: Follow quick implementation guide above
3. **Benchmark & Validate**: Measure improvements, ensure quality maintained
4. **Plan Phase 2**: vLLM integration and advanced caching
5. **Iterate**: Continuously monitor and optimize

---

## Additional Resources

- **Architecture**: [ARCHITECTURE.md](../architecture/ARCHITECTURE.md)
- **LLM Utilities**: [LLM_UTILITIES_LAYER.md](../architecture/LLM_UTILITIES_LAYER.md)
- **Simulation Orchestrator**: [SIMULATION_ORCHESTRATOR.md](../architecture/SIMULATION_ORCHESTRATOR.md)
- **Redis Caching**: [REDIS_COVERAGE_ANALYSIS.md](../data-storage/REDIS_COVERAGE_ANALYSIS.md)
- **Batch Operations**: [AGENT_POPULATION_OPTIMIZATION.md](../AGENT_POPULATION_OPTIMIZATION.md)

---

**Questions? Issues?**

Open a GitHub issue with the `performance` label or discuss in the optimization channel.

---

*Last Updated: January 10, 2026*
