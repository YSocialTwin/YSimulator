# Pluggable Memory Systems Roadmap

## Goal
Introduce a memory abstraction that allows YSimulator to run with:
1. no memory system (`none`),
2. native YSimulator semantic memory (`native`),
3. GhostKG-backed memory (`ghostkg`).

The selected backend must be switchable by configuration only, with no action-generator or orchestration code branching per backend.

## Scope and Assumptions
1. GhostKG can be modified as needed and is treated as an external convenience library.
2. GhostKG can use the same simulation DB and UUID-based identities.
3. Existing YSimulator service/repository architecture remains the integration backbone.
4. `none` mode is a first-class backend, not a disabled feature hack.

## Target Architecture
## Core Principle
`MemoryService` exposes one stable contract. Backends implement that contract.

## Backends
1. `NoMemoryBackend`: no-op implementation for `none` mode.
2. `NativeMemoryBackend`: YSimulator in-house semantic memory.
3. `GhostKGMemoryBackend`: adapter wrapping GhostKG APIs/data model.

## Selection
Backend resolved at server startup from config:
- `agent_memory.enabled=false` -> force `none`
- `agent_memory.enabled=true` + `agent_memory.backend in {none,native,ghostkg}` -> selected backend

## Runtime Contract (Backend Interface)
All backends must implement:
1. `initialize(simulation_context) -> None`
2. `ingest_event(agent_id, event, context) -> IngestResult`
3. `retrieve(agent_id, query, context) -> list[MemoryItemDTO]`
4. `reinforce(agent_id, memory_ids, context) -> ReinforceResult`
5. `forget_cycle(context) -> ForgetResult`
6. `health_check() -> BackendHealth`

## Non-Functional Contract
1. Methods must be idempotent where practical.
2. Backend failures must not crash core action processing in initial rollout.
3. Returned DTOs must be backend-neutral and deterministic.

## Phase Plan
## Phase 0: Contract and Config Freeze
### Deliverables
1. Define backend interface and DTOs.
2. Define config schema and backend selection rules.
3. Define fallback behavior (`ghostkg` unavailable -> fail fast or fallback by config policy).

### Checks
1. Static type checks for backend interface.
2. Config validation tests for all permutations.

### Success Criteria
1. Contract approved and immutable for Phase 1-3.
2. No existing simulation path behavior changes.

## Phase 1: Backend Skeletons and Wiring
### Deliverables
1. Add backend modules:
- `base.py`
- `none_backend.py`
- `native_backend.py` (stub if native not complete yet)
- `ghostkg_backend.py` (adapter stub)
2. Add `MemoryBackendFactory` for runtime backend resolution.
3. Wire factory into `MemoryService` and `service_factory.py`.
4. Expose server-level memory APIs through stable service call path.

### Checks
1. Unit tests for backend selection and fallback behavior.
2. Startup checks confirming selected backend and mode in logs.
3. `none` backend smoke test through full simulation run.

### Success Criteria
1. Backend switch is config-only.
2. `none` mode yields zero memory side effects and no regressions.

## Phase 2: Native Backend Production-Ready
### Deliverables
1. Implement native persistence/retrieval/forgetting.
2. Add periodic forgetting scheduler hook.
3. Integrate retrieval and reinforcement callbacks into action generation context.

### Checks
1. Ingestion/retrieval correctness tests.
2. Forgetting policy tests (time decay, capacity, eviction).
3. Performance baseline benchmarks for native mode.

### Success Criteria
1. Native backend satisfies contract and benchmark thresholds.
2. Existing tests pass with `none` and `native` modes.

## Phase 3: GhostKG Backend Production-Ready
### Deliverables
1. Implement GhostKG adapter mapping YSimulator events <-> triplets.
2. Enforce UUID identity mapping and shared DB integration.
3. Map retrieval outputs to common `MemoryItemDTO`.
4. Implement reinforcement/forgetting through GhostKG memory model.

### Checks
1. Contract parity tests (`native` vs `ghostkg` on same event fixtures).
2. Data integrity checks on shared DB schema boundaries.
3. Adapter resilience tests (library errors, partial failures, retries).

### Success Criteria
1. GhostKG backend passes contract suite.
2. Switching `native <-> ghostkg` requires no code changes.

## Phase 4: Client Integration Hardening
### Deliverables
1. Ensure all generators consume memory only through `ActionContext` callbacks.
2. Add token-budget-safe memory injection policy for LLM prompts.
3. Add no-memory behavior consistency for rule-based and LLM agents.

### Checks
1. Prompt-size guard tests.
2. Generator-level integration tests in all 3 modes.
3. End-to-end multi-client synchronization tests.

### Success Criteria
1. Same generator code works with all backends.
2. No prompt overflow regressions from memory inclusion.

## Phase 5: Observability, SLOs, and Rollout Gates
### Deliverables
1. Backend-tagged metrics (`backend=none|native|ghostkg`).
2. Health endpoints/log fields for backend status.
3. Runbook for mode switching and incident fallback to `none`.

### Checks
1. Metrics emitted in all modes.
2. Failure-injection tests (backend unavailable mid-run).
3. Rollback drill: switch to `none` without redeploy.

### Success Criteria
1. On-call can identify backend-specific failures quickly.
2. Safe rollback path validated.

## Required Test Matrix
## Functional Matrix
1. `none`: ingest/retrieve/reinforce/forget are no-op and safe.
2. `native`: full correctness.
3. `ghostkg`: full correctness + adapter mapping checks.

## Compatibility Matrix
1. DB backend: SQLite/PostgreSQL/MySQL.
2. Simulation mode: single-client and multi-client.
3. Agent type: rule-based and LLM.

## Regression Matrix
1. Existing action processors unaffected.
2. Recommendation and opinion systems unaffected.
3. Round/barrier synchronization unaffected.

## Performance and Reliability Gates
## Latency Targets
1. `retrieve` p95 within configured budget per action round.
2. `ingest_event` overhead bounded and non-blocking impact acceptable.

## Throughput Targets
1. No more than agreed simulation slowdown versus `none` baseline.
2. Forgetting cycle completes within daily/interval time budget.

## Reliability Targets
1. Backend exceptions do not corrupt action persistence path.
2. Deterministic behavior under repeated runs with fixed seeds/config.

## Evaluation Criteria for Backend Adoption
## Keep `none` Always Available
1. Must remain fully supported as operational fallback.

## Promote `native` Default If
1. Meets correctness and performance gates.
2. Lower operational complexity than GhostKG in your deployment context.

## Promote `ghostkg` Default If
1. Contract parity with native is demonstrated.
2. Memory-quality KPIs improve over native by agreed threshold.
3. Operational burden (dependency management, debugging, upgrades) remains acceptable.

## Suggested KPIs
1. Memory retrieval hit-rate.
2. Response/context coherence uplift (task-specific metric).
3. Memory staleness reduction rate.
4. Storage growth per 1k agents per simulated day.
5. Simulation throughput impact relative to `none`.

## Implementation Checklist (Executable)
1. Add backend interface and DTO definitions.
2. Add backend factory and mode resolution.
3. Implement `NoMemoryBackend`.
4. Wire service + server APIs to backend contract.
5. Implement native backend and tests.
6. Implement GhostKG adapter and tests.
7. Add generator integration checks for all modes.
8. Add metrics and health checks.
9. Run full matrix + benchmark suite.
10. Decide default backend using go/no-go criteria.

## Final Acceptance Criteria
1. Single config key switches among `none`, `native`, `ghostkg`.
2. No code changes required in generators/processors to switch backend.
3. All contract, integration, and regression tests pass for all modes.
4. Operational fallback to `none` is validated and documented.
