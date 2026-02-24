# Pluggable Memory Subsystem

This document describes YSimulator's semantic memory subsystem: architecture, implementation patterns, runtime pipelines, and configuration.

## Scope

The subsystem adds per-agent memory with forgetting and runtime backend selection:

- `none`: disabled (safe no-op)
- `native`: built-in SQL memory with decay/reinforcement
- `ghostkg`: external GhostKG adapter

Primary design goals:

- Keep memory optional and backward compatible.
- Keep a stable backend contract while allowing backend-specific internals.
- Keep simulation throughput predictable via bounded retrieval and periodic forgetting.

## Architecture

Core server components:

- `YSimulator/YServer/services/memory_config.py`: resolves `agent_memory` settings.
- `YSimulator/YServer/services/memory_service.py`: facade used by the server.
- `YSimulator/YServer/services/memory_backends/base.py`: backend interface and DTOs.
- `YSimulator/YServer/services/memory_backends/factory.py`: backend selection.
- `YSimulator/YServer/services/memory_backends/none_backend.py`: no-op backend.
- `YSimulator/YServer/services/memory_backends/native_backend.py`: SQL-backed semantic memory.
- `YSimulator/YServer/services/memory_backends/ghostkg_backend.py`: GhostKG adapter.

Server integration points:

- `YSimulator/YServer/server.py#get_agent_memory(...)`
- `YSimulator/YServer/server.py#record_memory_usage(...)`
- `YSimulator/YServer/server.py#ingest_memory_event(...)`
- `YSimulator/YServer/server.py#run_memory_forgetting(...)`
- periodic forgetting trigger in `submit_actions()` through `_maybe_run_memory_forgetting_cycle()`.

Client integration points:

- `YSimulator/YClient/client.py` injects memory hooks into action generators.
- generators fetch top-K memory items, inject bounded context into prompts, then reinforce used memories.

## Implementation Patterns

### 1) Strategy + Factory (backend swap)

`MemoryBackendFactory` maps backend string -> implementation. `MemoryService` stays backend-agnostic.

### 2) Facade boundary

The server calls only `MemoryService`; backend details never leak into server orchestration logic.

### 3) Stable DTO contract

Backends exchange typed DTOs (`MemoryItemDTO`, `IngestResult`, `ForgetResult`, etc.) to keep APIs consistent.

### 4) Fail-soft behavior

Memory errors are logged and degraded gracefully (empty retrieval / failed result object), avoiding simulation crashes.

### 5) Bounded prompt augmentation

Client prompt injection is constrained by:

- `retrieval_top_k`
- `prompt_memory_char_budget`
- `prompt_memory_item_char_limit`

This prevents unbounded token growth.

### 6) Controlled forgetting

Forgetting runs at configurable round intervals. Native backend combines:

- decay (`time_decay_lambda`)
- soft forget (`soft_forget_threshold`)
- hard delete (`hard_delete_after_days`)

## Runtime Pipelines

### Pipeline A: Action -> Ingestion

1. Client submits action.
2. Server processes action normally.
3. Server emits memory ingestion event to `MemoryService`.
4. Selected backend stores/updates memory.

### Pipeline B: Retrieval -> Prompt Injection -> Reinforcement

1. Generator requests memory context (`get_agent_memory`).
2. Backend returns ranked items.
3. Generator injects bounded snippets into the LLM prompt.
4. Generator reports used memory IDs (`record_memory_usage`).
5. Backend reinforces usage strength/confidence.

### Pipeline C: Periodic Forgetting

1. Server checks `forgetting_cycle_interval_rounds`.
2. If due, server runs `forget_cycle`.
3. Backend decays/forgets/deletes according to policy.
4. Stats are logged for observability.

### Pipeline D: Health and Diagnostics

- `get_memory_backend_status()` exposes backend health, enabled flag, and backend-specific details.

## Configuration

Main config location: `simulation_config.json` under `agent_memory`.

```json
{
  "agent_memory": {
    "enabled": true,
    "backend": "native",
    "retrieval_top_k": 5,
    "prompt_memory_char_budget": 600,
    "prompt_memory_item_char_limit": 140,
    "forgetting_cycle_interval_rounds": 24
  }
}
```

### Shared parameters

- `enabled`: master switch
- `backend`: `none | native | ghostkg`
- `retrieval_top_k`: retrieval limit for prompt context
- `prompt_memory_char_budget`: max total injected chars
- `prompt_memory_item_char_limit`: max chars per snippet
- `forgetting_cycle_interval_rounds`: forgetting cadence

### Native backend parameters

- `max_memories_per_agent`
- `time_decay_lambda`
- `reinforce_gain`
- `soft_forget_threshold`
- `hard_delete_after_days`

### GhostKG backend parameters

- `ghostkg.db_path`
- `ghostkg.db_url`
- `ghostkg.store_log_content`
- `ghostkg.extraction_mode`: `triplets | fast | llm`
- `ghostkg.ensure_datetime_clock`: `false` by default; preserves simulation tuple clock `(day, hour)` without synthetic datetime override.
- `ghostkg.relation_whitelist`
- LLM settings for `ghostkg.extraction_mode=llm` are inherited from top-level `llm` config.

Notes:

- `triplets` is the cheapest and most deterministic mode.
- `fast` uses GhostKG's low-cost extraction path.
- `llm` uses LLM extraction and has higher semantic flexibility/cost.
- GhostKG time sync supports simulation tuple time `(day, hour)`.
- Do not duplicate provider/model/API keys under `agent_memory.ghostkg`; use `simulation_config.llm`.

## Recommended Adoption Sequence

1. Start with `backend: none` and verify baseline behavior.
2. Enable `backend: native` with conservative defaults.
3. Validate retrieval quality and prompt budget impact.
4. Tune forgetting cadence/decay.
5. Introduce `backend: ghostkg` for KG-aware behavior.
6. Compare `triplets` vs `fast` vs `llm` on quality/cost.

## Validation and Success Criteria

Functional checks:

- Actions are ingested without regressions.
- Retrieval returns backend-consistent items.
- Reinforcement updates strength/relevance behavior.
- Forgetting runs only at configured intervals.
- `backend: none` reproduces baseline behavior.

Operational checks:

- No crash on backend failures.
- Prompt size remains within configured memory budgets.
- Health endpoint reports expected backend state.

Experiment checks:

- Compare action diversity and topic coherence with memory on/off.
- Compare quality/cost between native and GhostKG modes.

## Example Experiments

Two runnable example configurations are included:

- `example/memory_native_experiment/`
- `example/memory_ghostkg_experiment/`

Each example focuses on one backend and documents how to run it.

## Related Docs

- `docs/configuration/CONFIG.md`
- `docs/architecture/SEMANTIC_MEMORY_WITH_FORGETTING_DESIGN.md`
- `docs/architecture/PLUGGABLE_MEMORY_SYSTEM_ROADMAP.md`
