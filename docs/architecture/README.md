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

- **[DIAGRAMS.md](DIAGRAMS.md)** - Visual architecture diagrams (800+ lines)
  - Component diagrams
  - Sequence diagrams
  - Data flow diagrams
  - Multi-client coordination

- **[REPOSITORY_PATTERN.md](REPOSITORY_PATTERN.md)** - Data access patterns (360+ lines)
  - Repository pattern implementation
  - Service layer architecture
  - Clean architecture principles

### Refactoring Framework Documentation

These documents describe the modular frameworks created during the 5-phase server refactoring:

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

## Refactoring Impact

The 5-phase refactoring transformed the monolithic server architecture:

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| **server.py lines** | 3,114 | 1,966 | -1,148 (-37%) |
| **Largest method** | 476 lines | 70 lines | -406 (-85%) |
| **Direct DB calls** | 46 | 0 | -46 (-100%) |
| **Modules created** | 0 | 4 | +4 frameworks |
| **Unit tests** | ~27 | ~77 | +50 tests |

## Quick Links

- [Back to Documentation Index](../getting-started/INDEX.md)
- [Configuration Guide](../configuration/CONFIG.md)
- [Extending YSimulator](../development/EXTENDING.md)
- [Server Refactoring Report](../refactoring/SERVER_REFACTORING_REPORT.md)
- [Refactoring Audit Report](../refactoring/REFACTORING_AUDIT_REPORT.md)
