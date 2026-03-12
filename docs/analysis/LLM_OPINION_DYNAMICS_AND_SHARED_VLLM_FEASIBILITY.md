# Analysis: LLM Opinion Dynamics + Shared vLLM Pool Feasibility

Date: 2026-03-05

## 1) Does LLM opinion dynamics use batching when vLLM is enabled?

Short answer: **not effectively today**.

### What is implemented

- Opinion updates for interactions are computed via `OpinionCalculator._calculate_llm_evaluation(...)`.
- That path calls `llm_evaluation(...)`, which invokes `llm_manager.evaluate_opinion(...)` and then immediately does `ray.get(...)`.
- So each opinion-evaluation call is synchronous at that point.

Code evidence:
- `YSimulator/YClient/opinion/opinion_calculator.py:232-264`
- `YSimulator/YClient/opinion_dynamics/llm_evaluation.py:116-128`
- `YSimulator/YClient/llm_utils/llm_manager.py:312-343`

### What exists but is not wired end-to-end

- `VLLMService` already exposes both:
  - `evaluate_opinion(...)`
  - `evaluate_opinion_batch(...)`
- The batch processor has `_batch_evaluate_and_update_opinions(...)`, but it explicitly says it currently uses the standard path and has a TODO for real LLM batching.

Code evidence:
- `YSimulator/YClient/LLM_interactions/vllm_service.py:2136-2184` and `2184+`
- `YSimulator/YClient/simulation/batch_processor.py:1823-1861`

### Practical conclusion

- vLLM batching is active for several action flows (posts/comments/read/search), but **LLM opinion dynamics is still per-interaction/per-topic and blocking**.
- Therefore, when `opinion_dynamics.model_name = "llm_evaluation"`, opinion updates can still be a throughput bottleneck.

---

## 2) Feasibility: share one existing vLLM instance/pool across multiple clients/experiments

Short answer: **partially feasible now, with constraints; fully feasible with a small extension**.

## What already works today

The client startup already supports shared actor reuse via:
- `llm.reuse_actors`
- `llm.actor_name_prefix`
- `llm.num_actors`

Code evidence:
- `run_client.py:403-434`
- `YSimulator/YClient/llm_utils/load_balancer.py:101-124`, `140-161`, `426-449`

Behavior:
- If `reuse_actors=true`, clients attempt `ray.get_actor("{prefix}_vllm_{i}")`.
- If all expected actors exist, they are reused.
- If not found, a new set is created.

## Current limitations for cross-experiment sharing

1. **Namespace boundary**
- Clients connect to one Ray namespace from `simulation_config.json`.
- Actor lookup uses `ray.get_actor(name)` with no explicit namespace override.
- So sharing works only inside the same Ray namespace.

Code evidence:
- `run_client.py:365-367`
- `YSimulator/YClient/client.py:231`
- `YSimulator/YClient/llm_utils/load_balancer.py:110`, `431`

2. **Cannot target a specific existing pool robustly**
- Selection is only by naming convention (`actor_name_prefix`) + index.
- No pool registry or metadata validation (model, prompt set, tensor parallelism, etc.).

3. **Risk of accidental config mismatch**
- A client can reuse actors created with different model/prompts without validation.
- This can silently mix experiments with different LLM assumptions.

4. **Name-collision risk for multi-actor setups**
- Multi-actor creation uses deterministic names even when not reusing.
- Two experiments with same prefix/namespace can collide.

5. **Single-actor path asymmetry**
- For `num_actors==1` and `reuse_actors=false`, vLLM actor is detached but unnamed, so it cannot be intentionally reused by name later.

---

## Proposed solution (recommended)

## Goal
Allow multiple clients, including from different experiments, to explicitly reuse a chosen vLLM pool while preventing accidental mismatches.

## Configuration proposal
Add to client `simulation_config.json` under `llm`:

```json
"llm": {
  "backend": "vllm",
  "shared_pool": {
    "enabled": true,
    "pool_id": "gpu-pool-a",
    "namespace": "ysim_llm_pool",
    "expected_num_actors": 4,
    "strict": true,
    "create_if_missing": false
  }
}
```

## Runtime behavior proposal
1. Resolve actor names from `pool_id` (e.g., `ysim_vllm_{pool_id}_{i}`).
2. Lookup with namespace-aware API (`ray.get_actor(name, namespace=...)`).
3. Validate actor metadata (model, prompts hash/version, backend, tensor parallel size).
4. If `strict=true` and mismatch/missing actor: fail fast.
5. If `create_if_missing=true`: create pool in shared namespace and register metadata.

## Required code changes (small-to-medium)

1. **Namespace-aware lookup**
- Extend load balancer factory/constructor to accept `actor_namespace`.
- Use `ray.get_actor(name, namespace=actor_namespace)`.

2. **Actor metadata API**
- Add `get_service_metadata()` to `VLLMService` (and optionally `LLMService`) returning immutable config summary + prompt hash.

3. **Pool identity model**
- Replace loose `actor_name_prefix` with canonical `pool_id` + naming scheme.
- Keep backward compatibility by mapping old fields.

4. **Strict safety controls**
- `strict` and `create_if_missing` semantics.
- Better startup logs: reused pool id, namespace, actor count, metadata fingerprint.

5. **Operational utility (optional but useful)**
- Add a small CLI script to list available vLLM pools and metadata in a namespace.

---

## Recommendation

1. For immediate usage, you can already share vLLM actors by setting same:
- `namespace`
- `llm.actor_name_prefix`
- `llm.num_actors`
- `llm.reuse_actors=true` for reusing clients

2. For safe cross-experiment reuse, implement the `shared_pool` extension above (namespace-aware + metadata validation + strict mode). This avoids silent misconfiguration and makes "use this specific existing pool" explicit and reproducible.

---

## Suggested next implementation step

If approved, implement in this order:
1. Namespace-aware actor lookup and `shared_pool` config plumbing.
2. `get_service_metadata()` on vLLM actor + strict validation at attach time.
3. Optional pool-discovery utility command.

