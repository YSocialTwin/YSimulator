# YSimulator Documentation Index

**Version:** 3.1  
**Last Updated:** January 10, 2026

Welcome to the YSimulator documentation! This comprehensive guide will help you understand, configure, extend, and optimize your social media simulations.

> **📁 New Structure**: Documentation has been reorganized into thematic subdirectories for better navigation. See the [directory structure](#-documentation-directory-structure) below.
> 
> **✨ New in v3.1**: Added comprehensive performance optimization roadmap and bottleneck analysis (2,075 lines)
> 
> **✨ New in v3.0**: Added comprehensive YClient audit after Phase 1-6 refactoring (74% code reduction)

---

## 📚 Documentation Navigation

### 🚀 Quick Start Guides

| Document | Description | Best For |
|----------|-------------|----------|
| **[README](../../README.md)** | Project overview and quick start | New users, first-time setup |
| **[Configuration Guide](../configuration/CONFIG.md)** | Complete configuration reference (1,500+ lines) | Setting up simulations, customizing behavior |
| **[Architecture Overview](../architecture/ARCHITECTURE.md)** | System design and components (800+ lines) | Understanding how YSimulator works |

### 🤖 Agent Behavior & Types

| Document | Description | Key Topics |
|----------|-------------|------------|
| **[Agent Actions](../agents/AGENT_ACTIONS.md)** | Available actions and implementations (700+ lines) | POST, COMMENT, READ, SHARE, FOLLOW, LLM vs rule-based, action selection |
| **[Agent Types](../agents/AGENT_TYPES.md)** | Agent types and archetypes (750+ lines) | Standard vs page agents, LLM vs rule-based, Validator/Broadcaster/Explorer, profile variables |
| **[Agent Temporal Activities](../agents/AGENT_TEMPORAL_ACTIVITIES.md)** | Temporal patterns and dynamics (950+ lines) | hourly_activity, round_actions, activity_profiles, churn, new_agents |

### ⚙️ Core Features

| Document | Description | Key Topics |
|----------|-------------|------------|
| **[Recommendation Systems](../features/RECOMMENDATION_SYSTEMS.md)** | Content & follow recommendations (1,200+ lines) | 10 content modes, 5 follow strategies, algorithms, performance |
| **[Opinion Dynamics](../features/OPINION_DYNAMICS.md)** | Opinion modeling and evolution (1,200+ lines) | Bounded confidence, LLM evaluation, polarization |
| **[Opinion Dynamics Architecture](../features/OPINION_DYNAMICS_ARCHITECTURE.md)** | Adding new opinion models (guide) | Two-layer architecture, model development, complete examples |
| **[Interests & Topics](../features/INTERESTS.md)** | Interest management system (320+ lines) | Attention windows, sliding windows, topic extraction |
| **[Annotations](../features/ANNOTATION_IMPLEMENTATION.md)** | Emotion annotation system (200+ lines) | GoEmotions taxonomy, 28 emotions, sentiment analysis |

### 🚀 Performance & LLM Backends

| Document | Description | Key Topics |
|----------|-------------|------------|
| **[vLLM Integration Guide](../configuration/VLLM_INTEGRATION_GUIDE.md)** | Complete vLLM setup and configuration (450+ lines) | Backend selection, installation, configuration, troubleshooting, 8-30x speedup |
| **[vLLM Batch Inference](../features/VLLM_BATCH_INFERENCE.md)** | Comprehensive batch inference implementation (500+ lines) | Architecture, batching coverage, performance optimization, 10-50x speedup |
| **[vLLM Integration Summary](../features/VLLM_INTEGRATION_SUMMARY.md)** | Implementation summary and overview (500+ lines) | Phase 1 & 2 implementation, technical design, benchmarks, testing |
| **[vLLM Final Report](../features/VLLM_FINAL_REPORT.md)** | Complete implementation report (315+ lines) | Dual-model support, configuration schema, performance results, deployment guide |

### 🗄️ Data & Storage

| Document | Description | Focus Areas |
|----------|-------------|-------------|
| **[Database & Storage](../data-storage/REDIS_DATABASE_ANALYSIS.md)** | Redis/SQL hybrid architecture (480+ lines) | 89% Redis coverage, data structures, performance |
| **[Redis Integration](../data-storage/RECSYS_REDIS_SUPPORT.md)** | Redis support details (870+ lines) | Recommendation systems, opinion dynamics, caching strategies |

### 🏗️ Architecture & Design

| Document | Description | Contents |
|----------|-------------|----------|
| **[Architecture Overview](../architecture/ARCHITECTURE.md)** | System design and components | Coordinator-worker pattern, layered architecture |
| **[YClient Audit](../architecture/YCLIENT_AUDIT.md)** ✨ | Comprehensive YClient architecture (950+ lines) | Post-Phase 6 audit, all modules, integration patterns, usage examples |
| **[System Diagrams](../architecture/DIAGRAMS.md)** | Visual architecture (800+ lines) | Component diagrams, sequence diagrams, data flow |
| **[Repository Pattern](../architecture/REPOSITORY_PATTERN.md)** | Data access abstraction | Repository pattern, service layer, clean architecture |
| **[Action Processor Framework](../architecture/ACTION_PROCESSOR_FRAMEWORK.md)** | Modular action processing | Strategy pattern, action routing, extensibility |
| **[Recommendation Engine](../architecture/RECOMMENDATION_ENGINE.md)** | Content & follow recommendation architecture | Pluggable strategies, dual backend support |
| **[Opinion Dynamics Handler](../architecture/OPINION_DYNAMICS_HANDLER.md)** | Server-side opinion management | Profile-based initialization, database operations, Phase 3 |
| **[Coordination Layer](../architecture/COORDINATION_LAYER.md)** | Simulation orchestration | Client lifecycle, barrier synchronization, time advancement |
| **[Service Integration](../architecture/SERVICE_INTEGRATION.md)** | Complete service adoption | Direct service access, zero database coupling |

### 🛠️ Development & Extension

| Document | Description | Contents |
|----------|-------------|----------|
| **[Extending YSimulator](../development/EXTENDING.md)** | Developer guide (950+ lines) | Adding actions, extending behaviors, code examples |
| **[Code Formatting](../development/FORMATTING.md)** | Development standards | Black, isort, pre-commit hooks |
| **[Codebase Analysis](../development/CODEBASE_ANALYSIS.md)** | Code organization (1,660+ lines) | Architecture, patterns, testing infrastructure |

### 📖 Implementation Guides

Step-by-step guides for extending YSimulator with new features:

| Guide | Description | Est. Time | Key Topics |
|-------|-------------|-----------|------------|
| **[Adding New Actions](../development/ADDING_ACTIONS_GUIDE.md)** ✨ | Complete guide for new action types (Phase 1) | 1-2 hours | ActionGenerator pattern, LLM integration, OpinionManager, testing strategies |
| **[Opinion Dynamics Models](../features/OPINION_DYNAMICS_ARCHITECTURE.md#step-by-step-guide)** | Add new opinion algorithms (Phase 4) | 2-4 hours | Two-layer architecture, model development, bounded confidence examples |
| **[Recommendation Systems](../development/ADDING_RECSYS_GUIDE.md)** ✨ | Extend content/follow recommendations | 2-3 hours | Service layer, Redis caching, interest graph example, performance optimization |

**Quick Reference**:
- Want to add a new agent action (like "Quote" or "Poll")? → [Adding New Actions Guide](../development/ADDING_ACTIONS_GUIDE.md)
- Want to implement a custom opinion dynamics model? → [Opinion Dynamics Architecture](../features/OPINION_DYNAMICS_ARCHITECTURE.md#step-by-step-guide)
- Want to create a new recommendation algorithm? → [Recommendation Systems Guide](../development/ADDING_RECSYS_GUIDE.md)

### 📊 Logging & Monitoring

| Document | Description | Coverage |
|----------|-------------|----------|
| **[Logging Configuration](../logging/LOGGING_CONFIG.md)** | Logging setup guide (420+ lines) | Configuration, rotation, JSON format |
| **[Server Logging](../logging/SERVER_LOGGING.md)** | Server log analysis (380+ lines) | Request logs, performance metrics, troubleshooting |
| **[Action Logging](../logging/ACTION_LOGGING.md)** | Client action tracking (160+ lines) | Agent actions, summaries, analytics |

### 🔍 Analysis & Critical Paths

| Document | Description | Contents |
|----------|-------------|----------|
| **[Performance Optimization Roadmap](../analysis/PERFORMANCE_OPTIMIZATION_ROADMAP.md)** ✨ | Comprehensive performance analysis (1,685 lines) | 6 bottlenecks, 3-phase roadmap, 30x+ speedup potential, implementation strategies |
| **[Bottleneck Analysis Summary](../analysis/BOTTLENECK_ANALYSIS_SUMMARY.md)** ✨ | Quick reference guide (390 lines) | TL;DR findings, step-by-step implementation, quick wins (4x speedup in 1-2 weeks) |
| **[Critical Code Paths](../architecture/CRITICAL_CODE_PATHS.md)** | Performance-critical code (530+ lines) | Hot paths, optimization opportunities |
| **[Test Coverage Report](../testing/TEST_COVERAGE_REPORT.md)** | Testing status and progress (v3.1 with Phase 6) | Coverage metrics, all phases tested, recommendations |

### 🔧 Refactoring & Evolution

| Document | Description | Contents |
|----------|-------------|----------|
| **[Server Refactoring Report](../refactoring/SERVER_REFACTORING_REPORT.md)** | Complete server modernization | 5-phase transformation, metrics, patterns |
| **[Refactoring Audit Report](../refactoring/REFACTORING_AUDIT_REPORT.md)** | Comprehensive audit results | Test coverage, regression analysis, validation |
| **[Client Refactoring Report](../refactoring/CLIENT_REFACTORING_REPORT.md)** | Client architecture improvements (Phases 1-6) | Modularity, testing, maintainability, 74% code reduction |

---

## 🎯 Documentation by Use Case

### I Want To...

#### Get Started
1. **[README](../../README.md)** - Quick start and installation
2. **[Configuration Guide](../configuration/CONFIG.md)** - Set up your first simulation
3. **[Architecture Overview](../architecture/ARCHITECTURE.md)** - Understand the system
4. **[Agent Actions](../agents/AGENT_ACTIONS.md)** - Learn what agents can do

#### Configure Simulations
1. **[Configuration Guide](../configuration/CONFIG.md)** - All configuration options
   - Server configuration (database, Redis, Ray)
   - Client configuration (LLM, agents, behavior)
   - Agent archetypes and population dynamics
   - Multi-client setups
2. **[vLLM Integration Guide](../configuration/VLLM_INTEGRATION_GUIDE.md)** - Configure vLLM backend for high-performance LLM inference
3. **[Agent Types](../agents/AGENT_TYPES.md)** - Configure agent types and archetypes
4. **[Agent Temporal Activities](../agents/AGENT_TEMPORAL_ACTIVITIES.md)** - Configure temporal patterns and population dynamics
5. **[Opinion Dynamics](../features/OPINION_DYNAMICS.md)** - Configure opinion models
6. **[Recommendation Systems](../features/RECOMMENDATION_SYSTEMS.md)** - Configure recommendation strategies

#### Understand Agent Behavior
1. **[Agent Actions](../agents/AGENT_ACTIONS.md)** - Available actions and how they work
2. **[Agent Types](../agents/AGENT_TYPES.md)** - Agent types, archetypes, and differences
3. **[Agent Temporal Activities](../agents/AGENT_TEMPORAL_ACTIVITIES.md)** - When and how often agents act
4. **[Interests & Topics](../features/INTERESTS.md)** - Interest tracking and evolution
5. **[Opinion Dynamics](../features/OPINION_DYNAMICS.md)** - Opinion modeling and updates

#### Understand the System
1. **[Architecture Overview](../architecture/ARCHITECTURE.md)** - Component design
2. **[System Diagrams](../architecture/DIAGRAMS.md)** - Visual architecture
3. **[Database & Storage](../data-storage/REDIS_DATABASE_ANALYSIS.md)** - Data layer design
4. **[Redis Integration](../data-storage/RECSYS_REDIS_SUPPORT.md)** - Caching strategy

#### Optimize Performance
1. **[vLLM Integration Guide](../configuration/VLLM_INTEGRATION_GUIDE.md)** - High-performance LLM backend (8-30x speedup)
2. **[vLLM Batch Inference](../features/VLLM_BATCH_INFERENCE.md)** - Comprehensive batch inference (10-50x speedup)
3. **[Performance Optimization Roadmap](../analysis/PERFORMANCE_OPTIMIZATION_ROADMAP.md)** ✨ - Comprehensive performance analysis and optimization strategies
4. **[Bottleneck Analysis Summary](../analysis/BOTTLENECK_ANALYSIS_SUMMARY.md)** ✨ - Quick wins and step-by-step implementation guide
5. **[Database & Storage](../data-storage/REDIS_DATABASE_ANALYSIS.md)** - Redis coverage and performance
6. **[Redis Integration](../data-storage/RECSYS_REDIS_SUPPORT.md)** - Caching best practices
7. **[Recommendation Systems](../features/RECOMMENDATION_SYSTEMS.md)** - Performance benchmarks
8. **[Agent Types](../agents/AGENT_TYPES.md)** - Agent downcast optimization
9. **[Configuration Guide](../configuration/CONFIG.md)** - Agent archetypes and optimization

#### Extend Functionality
1. **[Extending YSimulator](../development/EXTENDING.md)** - Add new actions and behaviors
2. **[Agent Actions](../agents/AGENT_ACTIONS.md)** - Understand existing action implementations
3. **[Code Formatting](../development/FORMATTING.md)** - Development standards
4. **[Architecture Overview](../architecture/ARCHITECTURE.md)** - Component responsibilities

#### Monitor & Debug
1. **[Logging Configuration](../logging/LOGGING_CONFIG.md)** - Set up logging
2. **[Server Logging](../logging/SERVER_LOGGING.md)** - Analyze server logs
3. **[Action Logging](../logging/ACTION_LOGGING.md)** - Track agent actions
4. **[Configuration Guide](../configuration/CONFIG.md)** - Logging configuration options

#### Work with Features
- **Agent Behavior**: [Agent Actions](../agents/AGENT_ACTIONS.md) → [Agent Types](../agents/AGENT_TYPES.md) → [Agent Temporal Activities](../agents/AGENT_TEMPORAL_ACTIVITIES.md)
- **Recommendations**: [Recommendation Systems](../features/RECOMMENDATION_SYSTEMS.md) → [Redis Integration](../data-storage/RECSYS_REDIS_SUPPORT.md)
- **Opinions**: [Opinion Dynamics](../features/OPINION_DYNAMICS.md) → [Configuration Guide](../configuration/CONFIG.md)
- **Interests**: [Interests & Topics](../features/INTERESTS.md) → [Database & Storage](../data-storage/REDIS_DATABASE_ANALYSIS.md)
- **Annotations**: [Annotations](../features/ANNOTATION_IMPLEMENTATION.md) → [Database & Storage](../data-storage/REDIS_DATABASE_ANALYSIS.md)
- **vLLM Backend**: [vLLM Integration Guide](../configuration/VLLM_INTEGRATION_GUIDE.md) → [vLLM Batch Inference](../features/VLLM_BATCH_INFERENCE.md) → [vLLM Integration Summary](../features/VLLM_INTEGRATION_SUMMARY.md) → [vLLM Final Report](../features/VLLM_FINAL_REPORT.md)

---

## 📖 Documentation Map

### Level 1: Getting Started
```
README.md
    ↓
Configuration Guide (CONFIG.md)
    ↓
Architecture Overview (ARCHITECTURE.md)
```

### Level 2: Agent Behavior & Core Features
```
Agent Behavior
    ├── Agent Actions (AGENT_ACTIONS.md)
    ├── Agent Types (AGENT_TYPES.md)
    └── Agent Temporal Activities (AGENT_TEMPORAL_ACTIVITIES.md)

CONFIG.md
    ├── Recommendation Systems (RECOMMENDATION_SYSTEMS.md)
    ├── Opinion Dynamics (OPINION_DYNAMICS.md)
    ├── Interests & Topics (INTERESTS.md)
    └── Agent Configuration

ARCHITECTURE.md
    ├── System Diagrams (DIAGRAMS.md)
    ├── Database & Storage (REDIS_DATABASE_ANALYSIS.md)
    └── Redis Integration (RECSYS_REDIS_SUPPORT.md)
```

### Level 3: Advanced Topics
```
Extending YSimulator (EXTENDING.md)
    ├── Adding Actions
    ├── Custom Behaviors
    └── Code Standards (FORMATTING.md)

Database & Storage (REDIS_DATABASE_ANALYSIS.md)
    ├── Redis Coverage (89%)
    ├── Data Structures
    └── Performance Characteristics

Logging System
    ├── Logging Configuration (LOGGING_CONFIG.md)
    ├── Server Logging (SERVER_LOGGING.md)
    └── Action Logging (ACTION_LOGGING.md)
```

---

## 🔍 Feature Cross-Reference

### Recommendation Systems
- **Primary**: [Recommendation Systems](../features/RECOMMENDATION_SYSTEMS.md)
- **Configuration**: [Configuration Guide](../configuration/CONFIG.md#content-recommendation-system)
- **Redis Support**: [Redis Integration](../data-storage/RECSYS_REDIS_SUPPORT.md#recommendation-systems)
- **Architecture**: [Architecture Overview](../architecture/ARCHITECTURE.md#recommendation-systems)
- **Performance**: [Database & Storage](../data-storage/REDIS_DATABASE_ANALYSIS.md)

### Opinion Dynamics
- **Primary**: [Opinion Dynamics](../features/OPINION_DYNAMICS.md)
- **Configuration**: [Configuration Guide](../configuration/CONFIG.md#opinion-dynamics)
- **Redis Support**: [Redis Integration](../data-storage/RECSYS_REDIS_SUPPORT.md#opinion-dynamics)
- **Architecture**: [Architecture Overview](../architecture/ARCHITECTURE.md#opinion-dynamics)
- **Examples**: `example/llm_population_100_llm_opinion/`

### Agent Actions
- **Primary**: [Agent Actions](../agents/AGENT_ACTIONS.md)
- **Configuration**: [Configuration Guide](../configuration/CONFIG.md#action-likelihood-configuration)
- **Implementation**: [Extending YSimulator](../development/EXTENDING.md)
- **Archetypes**: [Agent Types](../agents/AGENT_TYPES.md#agent-archetypes)

### Agent Types
- **Primary**: [Agent Types](../agents/AGENT_TYPES.md)
- **Configuration**: [Configuration Guide](../configuration/CONFIG.md#agent-population-configuration)
- **Standard vs Page**: [Agent Types](../agents/AGENT_TYPES.md#standard-agents-vs-page-agents)
- **LLM vs Rule-Based**: [Agent Types](../agents/AGENT_TYPES.md#llm-based-vs-rule-based-agents)
- **Archetypes**: [Agent Types](../agents/AGENT_TYPES.md#agent-archetypes)

### Agent Temporal Activities
- **Primary**: [Agent Temporal Activities](../agents/AGENT_TEMPORAL_ACTIVITIES.md)
- **Configuration**: [Configuration Guide](../configuration/CONFIG.md#agent-behavior-configuration)
- **Churn & New Agents**: [Configuration Guide](../configuration/CONFIG.md#agent-population-dynamics)
- **Activity Patterns**: [Agent Temporal Activities](../agents/AGENT_TEMPORAL_ACTIVITIES.md#activity-profiles)

### Agent Archetypes
- **Primary**: [Agent Types](../agents/AGENT_TYPES.md#agent-archetypes)
- **Configuration**: [Configuration Guide](../configuration/CONFIG.md#agent-archetypes)
- **Actions**: [Agent Actions](../agents/AGENT_ACTIONS.md#action-selection-mechanism)
- **Architecture**: [Architecture Overview](../architecture/ARCHITECTURE.md#agent-archetypes)
- **Downcast Optimization**: [Agent Types](../agents/AGENT_TYPES.md#agent-downcast-feature)

### Interests & Topics
- **Primary**: [Interests & Topics](../features/INTERESTS.md)
- **Configuration**: [Configuration Guide](../configuration/CONFIG.md#agents-behavior-configuration)
- **Database**: [Database & Storage](../data-storage/REDIS_DATABASE_ANALYSIS.md#topics--interests)
- **Architecture**: [Architecture Overview](../architecture/ARCHITECTURE.md#interestmanager)

### Redis Integration
- **Primary**: [Redis Integration](../data-storage/RECSYS_REDIS_SUPPORT.md)
- **Analysis**: [Database & Storage](../data-storage/REDIS_DATABASE_ANALYSIS.md)
- **Configuration**: [Configuration Guide](../configuration/CONFIG.md#redis-configuration)
- **Performance**: [Recommendation Systems](../features/RECOMMENDATION_SYSTEMS.md#redis-vs-sql-backend-comparison)

### Multi-Client Simulations
- **Primary**: [Configuration Guide](../configuration/CONFIG.md#multi-client-synchronization)
- **Architecture**: [Architecture Overview](../architecture/ARCHITECTURE.md#coordination-mechanisms)
- **Diagrams**: [System Diagrams](../architecture/DIAGRAMS.md#multi-client-coordination)

### vLLM Backend Integration
- **Quick Start**: [vLLM Integration Guide](../configuration/VLLM_INTEGRATION_GUIDE.md)
- **Batch Inference**: [vLLM Batch Inference](../features/VLLM_BATCH_INFERENCE.md)
- **Implementation Summary**: [vLLM Integration Summary](../features/VLLM_INTEGRATION_SUMMARY.md)
- **Final Report**: [vLLM Final Report](../features/VLLM_FINAL_REPORT.md)
- **Configuration**: [Configuration Guide](../configuration/CONFIG.md#llm-configuration)
- **Performance**: [Bottleneck Analysis Summary](../analysis/BOTTLENECK_ANALYSIS_SUMMARY.md)
- **Example**: `example/llm_population_100_vllm/`

### Logging & Monitoring
- **Configuration**: [Logging Configuration](../logging/LOGGING_CONFIG.md)
- **Server Logs**: [Server Logging](../logging/SERVER_LOGGING.md)
- **Action Logs**: [Action Logging](../logging/ACTION_LOGGING.md)
- **Setup**: [Configuration Guide](../configuration/CONFIG.md#logging-configuration)

---

## 📊 Documentation Statistics

| Category | Files | Total Lines | Coverage |
|----------|-------|-------------|----------|
| **Getting Started** | 2 | 1,700 | README, Quick Start |
| **Configuration** | 1 | 1,550 | Complete reference |
| **Agent Behavior** | 3 | 2,400 | Actions, Types, Temporal Activities |
| **Core Features** | 4 | 3,700 | Recommendations, Opinions, Interests, Annotations |
| **Architecture & Design** | 8 | 5,500 | Architecture, Diagrams, Repository, Refactoring frameworks |
| **Data & Storage** | 2 | 1,350 | Redis analysis, integration |
| **Development** | 3 | 2,900 | Extending, Formatting, Codebase Analysis |
| **Logging** | 3 | 1,000 | Configuration, Server, Actions |
| **Analysis & Refactoring** | 5 | 2,600 | Critical paths, Test coverage, Refactoring reports |
| **Total** | 31 | 22,700 | Comprehensive coverage |

---

## 🚀 Recommended Reading Paths

### Path 1: New User
1. [README](../../README.md) - Overview and quick start
2. [Configuration Guide](../configuration/CONFIG.md) - Set up your simulation
3. [Agent Actions](../agents/AGENT_ACTIONS.md) - Learn what agents can do
4. [Agent Types](../agents/AGENT_TYPES.md) - Understand agent differences
5. [Architecture Overview](../architecture/ARCHITECTURE.md) - Understand the system
6. [Logging Configuration](../logging/LOGGING_CONFIG.md) - Monitor your simulation

### Path 2: Researcher
1. [Architecture Overview](../architecture/ARCHITECTURE.md) - System design
2. [Agent Actions](../agents/AGENT_ACTIONS.md) - Available agent behaviors
3. [Agent Types](../agents/AGENT_TYPES.md) - Agent types and archetypes
4. [Agent Temporal Activities](../agents/AGENT_TEMPORAL_ACTIVITIES.md) - Temporal patterns
5. [Recommendation Systems](../features/RECOMMENDATION_SYSTEMS.md) - Algorithms and strategies
6. [Opinion Dynamics](../features/OPINION_DYNAMICS.md) - Models and theory
7. [Database & Storage](../data-storage/REDIS_DATABASE_ANALYSIS.md) - Data structures
8. [Configuration Guide](../configuration/CONFIG.md) - Experiment configuration

### Path 3: Developer
1. [Architecture Overview](../architecture/ARCHITECTURE.md) - Component design
2. [System Diagrams](../architecture/DIAGRAMS.md) - Visual architecture
3. [Agent Actions](../agents/AGENT_ACTIONS.md) - Action implementations
4. [Extending YSimulator](../development/EXTENDING.md) - Add features
5. [Code Formatting](../development/FORMATTING.md) - Development standards
6. [Database & Storage](../data-storage/REDIS_DATABASE_ANALYSIS.md) - Data layer

### Path 4: Performance Engineer
1. [Database & Storage](../data-storage/REDIS_DATABASE_ANALYSIS.md) - Redis coverage
2. [Redis Integration](../data-storage/RECSYS_REDIS_SUPPORT.md) - Caching strategy
3. [Recommendation Systems](../features/RECOMMENDATION_SYSTEMS.md) - Performance benchmarks
4. [Agent Types](../agents/AGENT_TYPES.md) - Agent downcast optimization
5. [Configuration Guide](../configuration/CONFIG.md) - Optimization options
6. [Architecture Overview](../architecture/ARCHITECTURE.md) - System bottlenecks

### Path 5: System Administrator
1. [Configuration Guide](../configuration/CONFIG.md) - Setup and deployment
2. [Logging Configuration](../logging/LOGGING_CONFIG.md) - Monitoring setup
3. [Server Logging](../logging/SERVER_LOGGING.md) - Log analysis
4. [Architecture Overview](../architecture/ARCHITECTURE.md) - System components
5. [Redis Integration](../data-storage/RECSYS_REDIS_SUPPORT.md) - Redis deployment

---

## 🔧 Configuration Files Reference

### Core Configuration
- `server_config.json` → [Configuration Guide](../configuration/CONFIG.md#server-configuration)
- `simulation_config.json` → [Configuration Guide](../configuration/CONFIG.md#client-configuration)
- `agent_population.json` → [Configuration Guide](../configuration/CONFIG.md#agent-population-configuration)
- `llm_prompts.json` → [Configuration Guide](../configuration/CONFIG.md#llm-prompts-configuration)
- `network.csv` → [Configuration Guide](../configuration/CONFIG.md#social-network-topology)

### Configuration Examples
- `example/rule_population_100/` → Rule-based agents
- `example/llm_population_100/` → LLM agents with bounded confidence
- `example/llm_population_100_llm_opinion/` → LLM opinion evaluation
- `example/mixed_population_1000/` → Large-scale mixed population

---

## 💡 Key Concepts Index

| Concept | Primary Document | Related Documents |
|---------|------------------|-------------------|
| **Agent Actions** | [Agent Actions](../agents/AGENT_ACTIONS.md) | [Configuration](../configuration/CONFIG.md), [Extending](../development/EXTENDING.md) |
| **Agent Archetypes** | [Agent Types](../agents/AGENT_TYPES.md#agent-archetypes) | [Configuration](../configuration/CONFIG.md#agent-archetypes), [Actions](../agents/AGENT_ACTIONS.md#action-selection-mechanism) |
| **Agent Types** | [Agent Types](../agents/AGENT_TYPES.md) | [Configuration](../configuration/CONFIG.md) |
| **Activity Profiles** | [Agent Temporal Activities](../agents/AGENT_TEMPORAL_ACTIVITIES.md#activity-profiles) | [Configuration](../configuration/CONFIG.md) |
| **Barriers & Synchronization** | [Architecture Overview](../architecture/ARCHITECTURE.md#coordination-mechanisms) | [Configuration](../configuration/CONFIG.md#multi-client-synchronization) |
| **Bounded Confidence** | [Opinion Dynamics](../features/OPINION_DYNAMICS.md#bounded-confidence-model) | [Configuration](../configuration/CONFIG.md#opinion-dynamics) |
| **Churn & New Agents** | [Agent Temporal Activities](../agents/AGENT_TEMPORAL_ACTIVITIES.md#agent-churn) | [Configuration](../configuration/CONFIG.md#agent-population-dynamics) |
| **Content Recommendations** | [Recommendation Systems](../features/RECOMMENDATION_SYSTEMS.md#content-recommendation-system) | [Redis](../data-storage/RECSYS_REDIS_SUPPORT.md) |
| **Follow Recommendations** | [Recommendation Systems](../features/RECOMMENDATION_SYSTEMS.md#follow-recommendation-system) | [Architecture](../architecture/ARCHITECTURE.md) |
| **Heartbeat Mechanism** | [Architecture Overview](../architecture/ARCHITECTURE.md#heartbeat-mechanism) | [Configuration](../configuration/CONFIG.md#multi-client-synchronization) |
| **Hourly Activity** | [Agent Temporal Activities](../agents/AGENT_TEMPORAL_ACTIVITIES.md#hourly-activity-distribution) | [Configuration](../configuration/CONFIG.md) |
| **Interests & Attention** | [Interests & Topics](../features/INTERESTS.md) | [Database](../data-storage/REDIS_DATABASE_ANALYSIS.md), [Agent Types](../agents/AGENT_TYPES.md) |
| **LLM Integration** | [Configuration Guide](../configuration/CONFIG.md#llm-configuration) | [Architecture](../architecture/ARCHITECTURE.md#llm-service), [Agent Actions](../agents/AGENT_ACTIONS.md) |
| **Opinion Groups** | [Opinion Dynamics](../features/OPINION_DYNAMICS.md#opinion-groups) | [Configuration](../configuration/CONFIG.md) |
| **Page Agents** | [Agent Types](../agents/AGENT_TYPES.md#page-agents) | [Agent Actions](../agents/AGENT_ACTIONS.md#8-news-share-news-article) |
| **Redis Caching** | [Redis Integration](../data-storage/RECSYS_REDIS_SUPPORT.md) | [Database](../data-storage/REDIS_DATABASE_ANALYSIS.md) |
| **Round Actions** | [Agent Temporal Activities](../agents/AGENT_TEMPORAL_ACTIVITIES.md#round-actions) | [Agent Types](../agents/AGENT_TYPES.md) |
| **Sliding Windows** | [Redis Integration](../data-storage/RECSYS_REDIS_SUPPORT.md#sliding-window) | [Interests](../features/INTERESTS.md) |

---

## 📝 Documentation Coverage

### Recently Added (January 2026)

**Agent Behavior Documentation:**
1. **[Agent Actions](../agents/AGENT_ACTIONS.md)** - Comprehensive action reference with implementation details
2. **[Agent Types](../agents/AGENT_TYPES.md)** - Agent types, archetypes, and profile variables
3. **[Agent Temporal Activities](../agents/AGENT_TEMPORAL_ACTIVITIES.md)** - Temporal patterns, churn, and new agents

**Server Refactoring Documentation (Phases 1-5):**
4. **[Action Processor Framework](../architecture/ACTION_PROCESSOR_FRAMEWORK.md)** - Modular action processing architecture
5. **[Recommendation Engine](../architecture/RECOMMENDATION_ENGINE.md)** - Content & follow recommendation system
6. **[Opinion Dynamics Handler](../architecture/OPINION_DYNAMICS_HANDLER.md)** - Opinion management architecture
7. **[Coordination Layer](../architecture/COORDINATION_LAYER.md)** - Simulation orchestration framework
8. **[Service Integration](../architecture/SERVICE_INTEGRATION.md)** - Complete service adoption pattern

**Refactoring Reports:**
9. **[Server Refactoring Report](../refactoring/SERVER_REFACTORING_REPORT.md)** - 5-phase server modernization (37% reduction)
10. **[Refactoring Audit Report](../refactoring/REFACTORING_AUDIT_REPORT.md)** - Comprehensive audit results (77/77 tests passing)

### Previously Available
Based on analysis of the codebase and existing documentation, the following areas are comprehensively covered:
- ✅ Configuration and setup
- ✅ Architecture and system design
- ✅ Recommendation systems  
- ✅ Opinion dynamics
- ✅ Interest tracking
- ✅ Agent behavior and types
- ✅ Temporal activities
- ✅ Database and storage
- ✅ Development and extension
- ✅ Logging and monitoring
- ✅ **Server refactoring (Phases 1-5 complete)**
- ✅ **Modern architecture patterns (Repository, Service, Coordination)**
- ✅ **Comprehensive test coverage (77 tests, 100% passing)**

### Potential Future Additions
1. **API Reference** - Complete server/client API documentation
2. **Database Schema Guide** - Detailed schema reference with relationships
3. **Testing Guide** - Test strategies and examples
4. **Deployment Guide** - Production deployment best practices
5. **Troubleshooting Guide** - Common issues and solutions
6. **Migration Guide** - Upgrading between versions
7. **Performance Tuning** - Detailed optimization strategies
8. **Security Guide** - Security considerations and best practices

> **Note**: These are suggestions for future documentation expansion. The current documentation provides comprehensive coverage of all implemented features.

---

## 🤝 Contributing to Documentation

When adding or updating documentation:

1. **Update INDEX.md** - Add new documents to this index
2. **Add Cross-References** - Link to related documents
3. **Follow Structure** - Use consistent formatting and structure
4. **Include Examples** - Provide code examples and configurations
5. **Test Links** - Verify all hyperlinks work correctly
6. **Update Statistics** - Update the documentation statistics section

### Documentation Style Guide
- Use clear, concise language
- Include code examples where applicable
- Add navigation sections for long documents
- Cross-reference related documents
- Include version and update date
- Use markdown formatting consistently

---

## 📞 Getting Help

- **Start Here**: [README](../../README.md)
- **Configuration Questions**: [Configuration Guide](../configuration/CONFIG.md)
- **Technical Questions**: [Architecture Overview](../architecture/ARCHITECTURE.md)
- **Development Questions**: [Extending YSimulator](../development/EXTENDING.md)
- **Performance Questions**: [Database & Storage](../data-storage/REDIS_DATABASE_ANALYSIS.md)

---

**Last Updated:** January 5, 2026  
**Documentation Version:** 2.2  
**YSimulator Version:** 2.0

## 📁 Documentation Directory Structure

```
docs/
├── getting-started/     # Getting started guides and index
│   └── INDEX.md        # This file - comprehensive navigation
├── configuration/       # Configuration documentation
│   └── CONFIG.md       # Complete configuration reference
├── architecture/        # System architecture and design
│   ├── ARCHITECTURE.md                  # System design overview
│   ├── DIAGRAMS.md                     # Visual diagrams
│   ├── REPOSITORY_PATTERN.md           # Data access patterns
│   ├── ACTION_PROCESSOR_FRAMEWORK.md   # Phase 1 refactoring
│   ├── RECOMMENDATION_ENGINE.md        # Phase 2 refactoring
│   ├── OPINION_DYNAMICS_HANDLER.md     # Phase 3 refactoring (server)
│   ├── COORDINATION_LAYER.md           # Phase 4 refactoring
│   └── SERVICE_INTEGRATION.md          # Phase 5 refactoring
├── agents/             # Agent behavior documentation
│   ├── AGENT_ACTIONS.md           # Available actions
│   ├── AGENT_TYPES.md             # Agent types and archetypes
│   └── AGENT_TEMPORAL_ACTIVITIES.md # Temporal patterns
├── features/           # Core feature documentation
│   ├── RECOMMENDATION_SYSTEMS.md  # Content & follow recommendations
│   ├── OPINION_DYNAMICS.md        # Opinion modeling and evolution
│   ├── OPINION_DYNAMICS_ARCHITECTURE.md # Adding new opinion models (guide)
│   ├── INTERESTS.md               # Interest management
│   └── ANNOTATION_IMPLEMENTATION.md # Emotion annotations
├── data-storage/       # Database and storage
│   ├── REDIS_DATABASE_ANALYSIS.md # Redis/SQL hybrid architecture
│   └── RECSYS_REDIS_SUPPORT.md    # Redis integration details
├── development/        # Development guides
│   ├── EXTENDING.md           # How to extend YSimulator
│   ├── FORMATTING.md          # Code formatting standards
│   └── CODEBASE_ANALYSIS.md   # Code organization analysis
├── logging/            # Logging and monitoring
│   ├── LOGGING_CONFIG.md  # Logging configuration
│   ├── SERVER_LOGGING.md  # Server log analysis
│   └── ACTION_LOGGING.md  # Action log tracking
├── analysis/           # Analysis and testing
│   ├── CRITICAL_CODE_PATHS.md  # Performance-critical paths
│   └── TEST_COVERAGE_REPORT.md # Test coverage status
└── refactoring/        # Refactoring reports and documentation
    ├── SERVER_REFACTORING_REPORT.md   # 5-phase server modernization
    ├── REFACTORING_AUDIT_REPORT.md    # Comprehensive audit results
    └── CLIENT_REFACTORING_REPORT.md   # Client improvements
```
