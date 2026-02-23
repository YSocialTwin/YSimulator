# Semantic Memory with Forgetting for YSimulator Agents

## Objective
Design and integrate a semantic memory subsystem so agents in YSimulator can:
- retain distilled, reusable knowledge from interactions,
- retrieve relevant memory during action generation,
- forget stale or low-value memory over time,
- remain performant at large population sizes.

This document is an implementation blueprint aligned with the current architecture in:
- `YSimulator/YClient/client.py`
- `YSimulator/YClient/action_generators/base_generator.py`
- `YSimulator/YClient/simulation/round_executor.py`
- `YSimulator/YServer/server.py`
- `YSimulator/YServer/action_processors/*.py`
- `YSimulator/YServer/services/*.py`
- `YSimulator/YServer/repositories/*.py`

## Current Architecture Analysis (Relevant to Memory)
1. Action generation is client-side through `ActionGeneratorFactory` + generators (`YClient/action_generators/*`).
2. Action persistence and canonical state updates are server-side through `submit_actions()` and `ActionRouter` processors (`YServer/server.py`, `YServer/action_processors/*`).
3. Time is explicit via `(day, slot, round_id)` and managed centrally by server (`current_round_id`, `get_round_info()`).
4. Existing patterns already separate business logic and persistence (Service/Repository), making memory a natural new domain service.
5. Existing "decay" concepts already exist (follow-action decay, recsys recency), so forgetting can follow established config and observability patterns.

## Assumptions
1. Agent memory should be simulation-internal, deterministic enough for reproducibility, and independent from external long-term storage systems.
2. Semantic memory is distinct from:
- raw posts/comments/reactions (event history),
- opinion dynamics state (`agent opinions`),
- user interest counters.
3. Memory retrieval is needed for both rule-based and LLM agents, but LLM agents benefit most.
4. Redis may be enabled for speed, but SQL must remain the system of record for recoverability and consistency.
5. Forgetting should be gradual and configurable, not hard-coded deletion only.

## Requirements
### Functional Requirements
1. Capture candidate experiences from agent actions and observed feed content.
2. Convert experiences into compact semantic memory units (facts, beliefs, social affinity signals, topic associations).
3. Retrieve top-k relevant memory for a given action context (topic, target user, thread).
4. Apply forgetting using time decay + interference + capacity pressure.
5. Update memory strength by reinforcement when a memory is reused or reconfirmed.
6. Support memory invalidation/correction when newer contradictory signals appear.
7. Respect churn/new-agent lifecycle.

### Non-Functional Requirements
1. O(log N) or better retrieval behavior for per-agent memory lookups.
2. Bounded memory footprint per agent.
3. Backward-compatible rollout (feature flag off by default).
4. Full observability: hit-rate, forgetting rate, memory size, retrieval latency.
5. Testability via unit + integration tests in existing test architecture.

## Conceptual Memory Model
Use a **hybrid memory model**:
1. `Episodic Trace` (short-lived): raw event references from recent actions.
2. `Semantic Memory` (longer-lived): distilled statements used for reasoning.

Only semantic memory is queried during action generation.

### Semantic Memory Item
Each memory item represents a normalized proposition:
- `subject_type`: `self|agent|topic|source|post|thread`
- `subject_id`: UUID or canonical key
- `predicate`: e.g., `prefers`, `distrusts`, `agrees_with`, `topic_interest`, `high_engagement_with`
- `object_type`: `topic|agent|stance|source|content_style`
- `object_id/value`
- `confidence` in `[0,1]`
- `strength` in `[0,1]` (retrievability)
- `valence` in `[-1,1]` (optional sentiment polarity)
- `created_round_id`, `last_access_round_id`, `last_reinforced_round_id`
- `source_event_id` and `source_action_type`
- `embedding` (optional, for semantic nearest-neighbor retrieval)

## Forgetting Model
Forgetting should combine three effects:

1. Time Decay
- Exponential decay per round:
- `strength_t = strength_0 * exp(-lambda_time * delta_rounds)`
- configurable by topic/action class.

2. Interference
- New conflicting memories reduce strength of existing related memories:
- if same `(subject,predicate,object_type)` and contradictory object/value, apply:
- `strength_old *= (1 - interference_penalty)`

3. Capacity Pressure
- Per-agent memory budget (count and optional byte budget).
- Evict lowest `retention_score` when above budget.
- `retention_score = w1*strength + w2*confidence + w3*recency + w4*reuse_count - w5*conflict_penalty`

### Reinforcement
When memory is retrieved and used or reconfirmed by later events:
- `strength = min(1.0, strength + reinforce_gain)`
- update `last_reinforced_round_id` and `reuse_count`.

### Forget vs Archive
- `soft-forgotten`: strength below threshold, hidden from default retrieval.
- `hard-forgotten`: physically deleted after grace period or immediate under pressure.

## Storage and Data Schema
Add new tables in `YSimulator/YServer/classes/models.py`.

### SQL Tables
1. `agent_memory`
- `id` (UUID PK)
- `agent_id` (FK -> `user_mgmt.id`)
- `memory_type` (`semantic`)
- `subject_type`, `subject_id`, `predicate`, `object_type`, `object_value`
- `confidence`, `strength`, `valence`
- `reuse_count`
- `created_round_id`, `last_access_round_id`, `last_reinforced_round_id`
- `source_post_id`, `source_action_type`
- `embedding_vector` (nullable; serialized)
- `forgotten` (bool), `forgotten_on_round_id` (nullable)

2. `agent_memory_event`
- append-only audit trail of updates (created/reinforced/decayed/forgotten/conflicted)

3. `agent_memory_summary` (optional phase 2)
- periodic compressed summaries per topic/agent pair.

Indexes:
- `(agent_id, forgotten, strength DESC)`
- `(agent_id, predicate, object_type)`
- `(agent_id, last_access_round_id DESC)`
- `(agent_id, subject_id)`

### Redis Cache (Optional)
If Redis enabled:
- `ysim:memory:{agent_id}:top` (sorted set by retrieval score)
- `ysim:memory:{agent_id}:{memory_id}` (hash)
- `ysim:memory:dirty_agents` (set for async SQL sync)

SQL remains canonical.

## Service/Repository Design
Follow existing Service/Repository architecture.

### New Repository Interfaces (`base_repository.py`)
1. `MemoryRepository`
- `upsert_memory_item(...)`
- `get_memories(agent_id, filters, limit)`
- `reinforce_memory(memory_id, round_id, delta)`
- `apply_decay(agent_id, current_round_id)`
- `evict_memories(agent_id, policy)`
- `mark_forgotten(...)`

### New Implementations
1. `SQLMemoryRepository` in `sql_repository.py`
2. `RedisMemoryRepository` in `redis_repository.py` (optional, feature-gated)

### New Service
`MemoryService` in `YSimulator/YServer/services/memory_service.py`:
- ingestion and consolidation,
- retrieval ranking,
- forgetting scheduling,
- policy enforcement.

### Factory Wiring
Update `YSimulator/YServer/service_factory.py`:
- instantiate memory repository/service,
- inject into `OrchestratorServer`.

## Integration Pipelines
## Pipeline A: Memory Write (Action Ingestion)
Trigger point: `OrchestratorServer.submit_actions()` after each successful processor result.

Steps:
1. Action processed by existing processor (`POST/COMMENT/SHARE/FOLLOW/...`).
2. Build `MemoryEvent` from action + resolved context (topics, target user, sentiment, thread).
3. `MemoryService.ingest_event(agent_id, event, context)`:
- normalize into semantic propositions,
- merge/upsert or create new memory,
- reinforce if duplicate/consistent,
- apply contradiction penalties.
4. Emit memory metrics/logs.

Why here:
- server has canonical truth and IDs,
- single point for all action types,
- avoids divergence across clients.

## Pipeline B: Memory Retrieval (Pre-Action Context)
Trigger point: client action generation before generator decision/LLM call.

Integration points:
1. Extend `ActionContext` (`YClient/action_generators/base_generator.py`) with memory access hooks:
- `fetch_agent_memory_fn(agent_id, retrieval_context)`
- `record_memory_usage_fn(agent_id, memory_ids)`

2. In `SimulationClient._create_action_generator_factory()` (`YClient/client.py`), pass these callbacks (Ray calls to server memory APIs).

3. In generators (`post_generator.py`, `comment_generator.py`, `share_generator.py`, `reply_generator.py`, `read_generator.py`):
- request top-k memories relevant to topic/target/thread,
- inject concise memory snippets into LLM prompt attrs or rule decision logic.

4. After action completion, mark used memory IDs for reinforcement.

## Pipeline C: Scheduled Forgetting
Trigger point: end-of-day or every N rounds.

Integration points:
1. In server round advancement path (already centralized in coordination layer), call:
- `memory_service.run_forgetting_cycle(current_round_id, day, slot)`

2. Forgetting cycle:
- decay stale memories,
- apply capacity eviction,
- hard-delete long-soft-forgotten items,
- refresh Redis top-k cache.

3. Log summary:
- decayed_count, soft_forgotten_count, hard_deleted_count, mean_strength.

## Pipeline D: Churn/New Agent Lifecycle
1. On churn (`set_agent_churned` path): freeze memory updates; optionally keep data for analysis.
2. On new agent registration (`register_agents`): initialize blank semantic memory state.
3. On reactivation (if introduced later): unfreeze and apply catch-up decay.

## Retrieval and Ranking Strategy
Compute runtime retrieval score per candidate memory:
- `score = a*similarity + b*strength + c*confidence + d*recency + e*social_proximity`

Where:
- `similarity`: topic/target match (+ embedding similarity if enabled),
- `social_proximity`: same author/thread/network neighborhood bonuses.

Retrieval tiers:
1. Exact symbolic match (fast path).
2. Embedding nearest-neighbor fallback (optional).
3. Global priors if no memory hit.

## Configuration Additions
Add section to `simulation_config.json`:

```json
{
  "agent_memory": {
    "enabled": false,
    "retrieval_top_k": 5,
    "max_memories_per_agent": 500,
    "time_decay_lambda": 0.015,
    "reinforce_gain": 0.08,
    "interference_penalty": 0.2,
    "soft_forget_threshold": 0.12,
    "hard_delete_after_rounds": 336,
    "forgetting_cycle_interval_rounds": 24,
    "use_embeddings": false,
    "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
    "debug_log_memory": false
  }
}
```

Add optional server-level controls in `server_config.json` under `simulation.agent_memory` when central override is needed.

## API Surface (Server Actor)
Expose on `OrchestratorServer`:
1. `get_agent_memory(agent_id: str, query: dict, client_id: str = None) -> list`
2. `record_memory_usage(agent_id: str, memory_ids: list, client_id: str = None) -> bool`
3. `ingest_memory_event(agent_id: str, event: dict, client_id: str = None) -> bool` (optional explicit API)
4. `run_memory_forgetting(current_round_id: str = None) -> dict`

## Implementation Plan (Phased)
## Phase 1: Minimal Viable Semantic Memory
1. SQL schema + repository + service.
2. Ingest from `POST`, `COMMENT`, `SHARE`, `FOLLOW` only.
3. Retrieve by symbolic matching (no embeddings).
4. Time decay + capacity eviction.
5. Feature flag + metrics.

## Phase 2: Better Retrieval and Consolidation
1. Add embeddings and hybrid scoring.
2. Add daily semantic consolidation summaries.
3. Add contradiction reconciliation policies.

## Phase 3: Advanced Agent Cognition Hooks
1. Generator-specific memory usage strategies.
2. Memory-aware archetype behavior tuning.
3. Adaptive forgetting by archetype/personality.

## Testing Strategy
### Unit Tests
1. Memory score calculations and decay math.
2. Contradiction/interference updates.
3. Eviction ordering under capacity pressure.

### Integration Tests
1. Action submission creates/updates memory entries.
2. Retrieval returns expected top-k for topic/thread/author queries.
3. Forgetting cycle changes strengths and deletion status correctly.
4. Churn/new-agent lifecycle behavior.

### Performance Tests
1. Retrieval latency p50/p95 with 100/1k/10k agents.
2. Daily forgetting cycle runtime under large memory cardinality.

Suggested test files:
- `YSimulator/tests/test_agent_memory_service.py`
- `YSimulator/tests/test_agent_memory_repository.py`
- `YSimulator/tests/test_agent_memory_integration.py`
- `YSimulator/tests/test_agent_memory_forgetting.py`

## Observability
Add metrics/logging fields:
1. `memory_items_total`
2. `memory_retrieval_requests_total`
3. `memory_retrieval_hit_rate`
4. `memory_forgetting_soft_total`
5. `memory_forgetting_hard_total`
6. `memory_avg_retrieval_latency_ms`

Log with existing JSON logging style used by server/client.

## Risks and Mitigations
1. Risk: memory bloat at scale.
- Mitigation: strict per-agent budget + hard-delete window + Redis top-k cache.

2. Risk: noisy/incorrect memories degrade behavior.
- Mitigation: confidence gating, contradiction penalties, minimum evidence thresholds.

3. Risk: prompt inflation for LLM agents.
- Mitigation: top-k cap + compressed memory snippets + token budget in generators.

4. Risk: added write/read overhead.
- Mitigation: async/batched ingestion where possible and caching hot memory subsets.

## Minimal Code Change Map
1. Models
- `YSimulator/YServer/classes/models.py` (new memory tables)

2. Repositories
- `YSimulator/YServer/repositories/base_repository.py` (new memory interface)
- `YSimulator/YServer/repositories/sql_repository.py` (SQL implementation)
- `YSimulator/YServer/repositories/redis_repository.py` (optional Redis implementation)

3. Services
- `YSimulator/YServer/services/memory_service.py` (new)
- `YSimulator/YServer/service_factory.py` (wiring)

4. Server actor
- `YSimulator/YServer/server.py` (APIs + submit_actions hook + forgetting schedule hook)

5. Client context and generators
- `YSimulator/YClient/action_generators/base_generator.py` (memory callbacks in ActionContext)
- `YSimulator/YClient/client.py` (inject memory callbacks)
- `YSimulator/YClient/action_generators/post_generator.py`
- `YSimulator/YClient/action_generators/comment_generator.py`
- `YSimulator/YClient/action_generators/share_generator.py`
- `YSimulator/YClient/action_generators/reply_generator.py`

6. Configuration docs
- `docs/configuration/CONFIG.md` (new `agent_memory` section)

## Acceptance Criteria
1. With `agent_memory.enabled=false`, behavior is unchanged.
2. With memory enabled, agents retrieve relevant memories in action generation.
3. Forgetting reduces stale memory volume over time with bounded per-agent memory count.
4. End-to-end simulation remains stable with existing tests + new memory tests passing.

## GhostKG Integration Analysis
This section extends the design with the additional requirement to evaluate and potentially integrate:
- GhostKG repository: `https://github.com/GiulioRossetti/GhostKG`

The assessment is based on GhostKG's current code/docs (README, API docs, storage schema, FSRS implementation).

## What GhostKG Adds
GhostKG provides capabilities that overlap with and can accelerate this design:
1. Dynamic knowledge graphs with triplets (`subject-relation-object`).
2. FSRS-based memory decay/retention (`stability`, `difficulty`, `retrievability`).
3. Time-aware APIs including round-like `(day, hour)` simulation time.
4. Multi-agent manager abstraction (`AgentManager`) and direct agent API (`GhostAgent`).
5. SQLAlchemy-backed storage with SQLite/PostgreSQL/MySQL support.
6. Optional context caching and visualization/export tooling.

## Fit With YSimulator
## Strong Alignment
1. Both systems are simulation-oriented and time-aware.
2. Both already use SQLAlchemy and support similar DB backends.
3. GhostKG's triplet+memory model is compatible with YSimulator's proposed semantic proposition model.
4. GhostKG external API mode fits YSimulator's architecture because YSimulator already owns LLM orchestration and action flow.

## Friction Points
1. YSimulator is UUID-first and service/repository-layered; GhostKG is agent-name-centric in several APIs.
2. YSimulator's source of truth is `OrchestratorServer`; GhostKG can manage its own DB schema/tables.
3. YSimulator currently stores simulation time as round/day/slot in `rounds`; GhostKG can use datetime and `(day, hour)` but needs strict mapping policy.
4. Triplet extraction and knowledge semantics must be kept deterministic across multi-client distributed execution.

## Pros and Cons of Using GhostKG
## Pros
1. Faster path to realistic forgetting via FSRS (better than ad-hoc decay only).
2. Mature conceptual model for memory as graph relations, not isolated key-value facts.
3. Built-in memory state variables (`stability`, `difficulty`, review state) improve interpretability.
4. Multi-database portability and tested storage layer reduce custom infrastructure effort.
5. External API mode allows YSimulator to keep existing LLM/reply pipeline unchanged.
6. Visualization/export tools can help validate memory dynamics empirically.

## Cons
1. Additional dependency and operational surface area (new package lifecycle, version compatibility).
2. Potential schema duplication (YSimulator tables + `kg_*` tables) and data sync complexity.
3. Mapping effort from YSimulator actions/events to GhostKG triplets and ratings.
4. Potential performance overhead if every action triggers full KG writes without batching.
5. Semantic mismatch risk if relation vocabulary is not standardized.
6. Tight coupling risk if core simulation logic directly depends on GhostKG internals rather than an adapter.

## Decision Recommendation
Use GhostKG as an optional backend behind a YSimulator memory adapter, not as a hard replacement of core server/service abstractions.

Rationale:
1. Preserves current architecture and rollout safety.
2. Enables A/B testing against the native memory implementation.
3. Minimizes lock-in and allows fallback to existing design if needed.

## Integration Architecture Options
## Option A: Native YSimulator Memory Only
No GhostKG integration.

Use when:
1. Minimal dependencies are required.
2. Full control and schema consistency are top priority.

## Option B: GhostKG as Primary Memory Engine (Not Recommended First)
Server delegates memory storage/retrieval/forgetting directly to GhostKG APIs.

Risk:
1. High coupling and migration complexity.

## Option C: Hybrid Adapter (Recommended)
Add `GhostKGMemoryAdapter` under YSimulator service layer.

Pattern:
1. `MemoryService` exposes YSimulator-stable interface.
2. Backend selected by config:
- `backend = native | ghostkg`.
3. `ghostkg` backend translates events <-> triplets <-> memory retrieval format.
4. Existing action processors and generators stay unchanged except for using MemoryService APIs.

## Proposed Integration Pipeline (GhostKG Hybrid Adapter)
## Phase G0: Compatibility and Contract Lock
Deliverables:
1. Define backend-agnostic interface in `MemoryService`:
- `ingest_event(...)`
- `retrieve(...)`
- `reinforce(...)`
- `forget_cycle(...)`
2. Define canonical memory DTO used by client generators.
3. Freeze relation vocabulary and rating mapping rules.

Acceptance:
1. Same tests pass for both `native` and `ghostkg` backends.

## Phase G1: GhostKG Adapter on Server
Implementation:
1. Add new module:
- `YSimulator/YServer/services/memory_backends/ghostkg_adapter.py`
2. Initialize one GhostKG manager/agent registry per server process.
3. Maintain deterministic agent identity mapping:
- YSimulator `agent_id (UUID)` -> GhostKG `owner_id` (store UUID string as name).
4. Keep storage in same DB where possible (GhostKG uses `kg_*` prefixed tables).

Data mapping:
1. Action -> triplets examples:
- `POST(topic=t)` by A: `(I, posts_about, t)` for agent A
- `COMMENT` by A on B's post p about t: `(B, discusses, t)`, `(I, engaged_with, B)`
- `FOLLOW` A->B: `(I, follows, B)`
- `SHARE` A of topic t: `(I, amplifies, t)`
2. Sentiment and confidence map into edge sentiment and rating.

Acceptance:
1. Action submission updates GhostKG tables without affecting existing action persistence.

## Phase G2: Retrieval Wiring to Action Generation
Implementation:
1. `OrchestratorServer.get_agent_memory(...)` delegates to backend adapter.
2. `SimulationClient._create_action_generator_factory()` injects memory callbacks.
3. Generators request context via existing abstraction and receive normalized memory snippets.

Retrieval policy:
1. Query GhostKG context (`get_context`/memory view) by topic + optional partner.
2. Convert returned context into bounded prompt payload.
3. Track used memory IDs for reinforcement.

Acceptance:
1. LLM prompts include memory context when enabled.
2. Token usage remains under configurable ceiling.

## Phase G3: Forgetting Cycle and Reinforcement
Implementation:
1. Run scheduled forgetting from server round/day advancement hook.
2. Convert usage signals to FSRS ratings:
- successful reuse: `Good`/`Easy`
- contradiction or failed reuse: `Hard`/`Again`
3. Persist forgetting metrics in server logs.

Acceptance:
1. Retrievability distribution shifts over time.
2. Memory volume remains bounded without manual cleanup.

## Phase G4: Evaluation and Hardening
1. A/B test `native` vs `ghostkg` on:
- coherence of agent replies,
- retrieval hit-rate,
- simulation throughput,
- DB growth rate.
2. Decide default backend after benchmark threshold is met.

## Mapping Rules (YSimulator <-> GhostKG)
## Identity and Time
1. `owner_id` = YSimulator `agent_id` UUID string.
2. Use round-based clock mapping:
- YSimulator `day` -> GhostKG `sim_day`
- YSimulator `slot` -> GhostKG `sim_hour`

## Memory Strength Model Mapping
1. Native `strength/confidence` fields map to GhostKG FSRS state:
- confidence influences initial rating on insert.
- strength approximated from retrievability when converting back.
2. Contradictions reduce rating to `Hard/Again` for affected triplets.

## Retrieval Output Mapping
Normalize GhostKG retrieval into YSimulator DTO:
1. `memory_text` (concise statement)
2. `relevance_score`
3. `source_triplet`
4. `retrievability`
5. `sentiment`
6. `memory_id`

## Configuration Extension for GhostKG
Add to `simulation_config.json`:

```json
{
  "agent_memory": {
    "enabled": true,
    "backend": "ghostkg",
    "retrieval_top_k": 5,
    "max_memories_per_agent": 500,
    "forgetting_cycle_interval_rounds": 24,
    "ghostkg": {
      "db_url": null,
      "store_log_content": false,
      "fast_mode": false,
      "relation_whitelist": [
        "posts_about",
        "engaged_with",
        "follows",
        "amplifies",
        "agrees_with",
        "disagrees_with"
      ],
      "rating_mapping": {
        "reinforce_strong": "Easy",
        "reinforce_normal": "Good",
        "weak_signal": "Hard",
        "contradiction": "Again"
      }
    }
  }
}
```

## Code Change Plan for GhostKG Path
1. Add backend interface and adapter:
- `YSimulator/YServer/services/memory_backends/base.py`
- `YSimulator/YServer/services/memory_backends/native_backend.py`
- `YSimulator/YServer/services/memory_backends/ghostkg_adapter.py`

2. Extend service factory wiring:
- `YSimulator/YServer/service_factory.py`

3. Extend server actor APIs:
- `YSimulator/YServer/server.py`

4. Reuse existing client integration points already proposed in this document:
- `YSimulator/YClient/action_generators/base_generator.py`
- `YSimulator/YClient/client.py`
- action generators for prompt/context injection.

5. Dependency/config updates:
- `requirements.txt` or optional extras handling.
- `docs/configuration/CONFIG.md` updates.

## Risk Register (GhostKG-Specific)
1. Version drift between GhostKG and YSimulator.
- Mitigation: pin GhostKG version and run contract tests in CI.

2. Cross-schema transaction issues.
- Mitigation: keep memory writes isolated and idempotent; do not block action commit on memory failure initially.

3. Latency spikes under high action volume.
- Mitigation: batch ingest per round and asynchronous reinforcement updates.

4. Semantic noise from weak triplet extraction.
- Mitigation: whitelist relations + confidence threshold + periodic pruning.

## Testing Plan Extension (GhostKG Backend)
1. Backend contract tests:
- same input events, equivalent retrieval behavior for native and ghostkg backends.

2. Integration tests:
- end-to-end `submit_actions -> memory ingest -> retrieval -> reinforcement`.

3. Migration tests:
- toggling `backend` does not break simulations.

4. Performance tests:
- throughput and latency impact with 1k/5k/10k agents.

Suggested additional test files:
- `YSimulator/tests/test_memory_backend_contract.py`
- `YSimulator/tests/test_memory_backend_ghostkg.py`
- `YSimulator/tests/test_memory_backend_switching.py`

## Go/No-Go Criteria for Adopting GhostKG by Default
Promote `ghostkg` as default only if all are met:
1. Simulation throughput degradation <= 10% versus native backend.
2. Memory retrieval hit-rate improvement >= 15% on benchmark scenarios.
3. No regression in existing action/recommendation/opinion tests.
4. DB growth remains within configured storage budget over long runs.
