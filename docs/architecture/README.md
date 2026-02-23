# Architecture Documentation

This directory contains system architecture and design pattern documentation.

## Files

### Core Architecture

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design overview (960+ lines)
  - High-level architecture
  - Component details
  - Data flow
  - Coordination mechanisms
  - Technology stack

- **[CRITICAL_CODE_PATHS.md](CRITICAL_CODE_PATHS.md)** - Performance-critical code (530+ lines)
  - Hot paths and optimization opportunities
  - Critical code sections
  - Performance considerations

- **[DIAGRAMS.md](DIAGRAMS.md)** - Visual architecture diagrams (800+ lines)
  - Component diagrams
  - Sequence diagrams
  - Data flow diagrams
  - Multi-client coordination

- **[REPOSITORY_PATTERN.md](REPOSITORY_PATTERN.md)** - Data access patterns (360+ lines)
  - Repository pattern implementation
  - Service layer architecture
  - Clean architecture principles

### Memory Architecture

- **[SEMANTIC_MEMORY_WITH_FORGETTING_DESIGN.md](SEMANTIC_MEMORY_WITH_FORGETTING_DESIGN.md)** - Semantic memory design
  - assumptions and requirements
  - native and GhostKG integration options
  - retrieval/reinforcement/forgetting flows

- **[PLUGGABLE_MEMORY_SYSTEM_ROADMAP.md](PLUGGABLE_MEMORY_SYSTEM_ROADMAP.md)** - Implementation roadmap
  - phased rollout plan
  - validation checks and success criteria

### Refactoring Framework Documentation

These documents describe the modular frameworks created during refactoring:

#### Server Refactoring (5 Phases - All Complete)

- **[ACTION_PROCESSOR_FRAMEWORK.md](ACTION_PROCESSOR_FRAMEWORK.md)** - Phase 1 refactoring (270+ lines)
  - Strategy pattern for action processing
  - BaseActionProcessor and ActionRouter
  - 6 specialized processors (POST, COMMENT, SHARE, FOLLOW, UNFOLLOW, REACTION)
  - Reduced submit_actions() from 476 to 70 lines (85% reduction)

- **[RECOMMENDATION_ENGINE.md](RECOMMENDATION_ENGINE.md)** - Phase 2 refactoring (280+ lines)
  - ContentRecommender with 10+ strategies
  - FollowRecommender with 5 algorithms
  - Dual backend support (SQL and Redis)
  - Reduced recommendation methods by 86%

- **[OPINION_DYNAMICS_HANDLER.md](OPINION_DYNAMICS_HANDLER.md)** - Phase 3 refactoring (300+ lines)
  - OpinionHandler for opinion management
  - Profile-based opinion initialization
  - LLM integration support
  - Neighbor opinion retrieval

- **[COORDINATION_LAYER.md](COORDINATION_LAYER.md)** - Phase 4 refactoring (520+ lines)
  - ClientManager for client lifecycle
  - BarrierHandler for synchronization
  - RoundManager for time advancement
  - ArchetypeManager for transitions
  - Reduced coordination methods by 77-93%

- **[SERVICE_INTEGRATION.md](SERVICE_INTEGRATION.md)** - Phase 5 refactoring (480+ lines)
  - Complete migration to Repository/Service pattern
  - Direct service access (10 services exposed)
  - Eliminated 46 direct database calls (100%)
  - Clear service boundaries

#### Client Refactoring (3 Phases Complete)

- **[CLIENT_REFACTORING_REPORT.md](../refactoring/CLIENT_REFACTORING_REPORT.md)** - Phases 1-3 overview (1,300+ lines)
  - Phase 1: Action Generator Framework (10 generators, +10 tests)
  - Phase 2: Simulation Orchestrator (5 modules, +9 tests)
  - Phase 3: LLM Utilities Layer (5 modules, +32 tests)
  - Complete client modernization details

- **[SIMULATION_ORCHESTRATOR.md](SIMULATION_ORCHESTRATOR.md)** - Phase 2 client refactoring (430+ lines)
  - Simulator for main coordination
  - RoundExecutor for per-round execution
  - AgentScheduler for agent selection
  - BatchProcessor for LLM batching
  - LifecycleManager for agent lifecycle
  - Reduced run() from 297 to 18 lines (94% reduction)

- **[LLM_UTILITIES_LAYER.md](LLM_UTILITIES_LAYER.md)** - Phase 3 client refactoring (430+ lines)
  - LLMManager for unified LLM interface (11 methods)
  - BatchHandler for scatter/gather pattern
  - RetryHandler for automatic retry with exponential backoff
  - ResponseParser for response validation
  - CostTracker for usage monitoring and logging
  - 100% LLM call coverage achieved

## Refactoring Impact

### Server Refactoring (5 Phases Complete)

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| **server.py lines** | 3,114 | 1,966 | -1,148 (-37%) |
| **Largest method** | 476 lines | 70 lines | -406 (-85%) |
| **Direct DB calls** | 46 | 0 | -46 (-100%) |
| **Modules created** | 0 | 4 | +4 frameworks |
| **Unit tests** | ~27 | ~77 | +50 tests |

### Client Refactoring (3 Phases Complete)

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| **client.py lines** | 2,924 | 2,161 | -763 (-26%) |
| **action_executor.py** | 952 | 0 (deleted) | -952 (-100%) |
| **run() method** | 297 lines | 18 lines | -279 (-94%) |
| **Modules created** | 0 | 3 packages | +20 new modules |
| **Unit tests** | 2 | 53 | +51 tests |
| **LLM coverage** | Scattered | 100% | All calls centralized |

## Quick Links

- [Back to Documentation Index](../getting-started/INDEX.md)
- [Configuration Guide](../configuration/CONFIG.md)
- [Extending YSimulator](../development/EXTENDING.md)
- [Server Refactoring Report](../refactoring/SERVER_REFACTORING_REPORT.md)
- [Refactoring Audit Report](../refactoring/REFACTORING_AUDIT_REPORT.md)
