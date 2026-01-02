# YSimulator Documentation Index

**Version:** 2.0  
**Last Updated:** January 1, 2026

Welcome to the YSimulator documentation! This comprehensive guide will help you understand, configure, extend, and optimize your social media simulations.

---

## 📚 Documentation Navigation

### Quick Start Guides

| Document | Description | Best For |
|----------|-------------|----------|
| **[README](../README.md)** | Project overview and quick start | New users, first-time setup |
| **[Configuration Guide](CONFIG.md)** | Complete configuration reference (1,500+ lines) | Setting up simulations, customizing behavior |
| **[Architecture Overview](ARCHITECTURE.md)** | System design and components (800+ lines) | Understanding how YSimulator works |

### Core Features

| Document | Description | Key Topics |
|----------|-------------|------------|
| **[Recommendation Systems](RECOMMENDATION_SYSTEMS.md)** | Content & follow recommendations (1,200+ lines) | 10 content modes, 5 follow strategies, algorithms, performance |
| **[Opinion Dynamics](OPINION_DYNAMICS.md)** | Opinion modeling and evolution (1,200+ lines) | Bounded confidence, LLM evaluation, polarization |
| **[Interests & Topics](INTERESTS.md)** | Interest management system (300+ lines) | Attention windows, sliding windows, topic extraction |

### System Components

| Document | Description | Focus Areas |
|----------|-------------|-------------|
| **[Database & Storage](REDIS_DATABASE_ANALYSIS.md)** | Redis/SQL hybrid architecture (480+ lines) | 89% Redis coverage, data structures, performance |
| **[Redis Integration](RECSYS_REDIS_SUPPORT.md)** | Redis support details (870+ lines) | Recommendation systems, opinion dynamics, caching strategies |
| **[Annotations](ANNOTATION_IMPLEMENTATION.md)** | Emotion annotation system (200+ lines) | GoEmotions taxonomy, 28 emotions, sentiment analysis |

### Development & Extension

| Document | Description | Contents |
|----------|-------------|----------|
| **[Extending YSimulator](EXTENDING.md)** | Developer guide (950+ lines) | Adding actions, extending behaviors, code examples |
| **[System Diagrams](DIAGRAMS.md)** | Visual architecture (800+ lines) | Component diagrams, sequence diagrams, data flow |
| **[Code Formatting](FORMATTING.md)** | Development standards | Black, isort, pre-commit hooks |

### Logging & Monitoring

| Document | Description | Coverage |
|----------|-------------|----------|
| **[Logging Configuration](LOGGING_CONFIG.md)** | Logging setup guide (420+ lines) | Configuration, rotation, JSON format |
| **[Server Logging](SERVER_LOGGING.md)** | Server log analysis (380+ lines) | Request logs, performance metrics, troubleshooting |
| **[Action Logging](ACTION_LOGGING.md)** | Client action tracking (160+ lines) | Agent actions, summaries, analytics |

---

## 🎯 Documentation by Use Case

### I Want To...

#### Get Started
1. **[README](../README.md)** - Quick start and installation
2. **[Configuration Guide](CONFIG.md)** - Set up your first simulation
3. **[Architecture Overview](ARCHITECTURE.md)** - Understand the system

#### Configure Simulations
1. **[Configuration Guide](CONFIG.md)** - All configuration options
   - Server configuration (database, Redis, Ray)
   - Client configuration (LLM, agents, behavior)
   - Agent archetypes and population dynamics
   - Multi-client setups
2. **[Opinion Dynamics](OPINION_DYNAMICS.md)** - Configure opinion models
3. **[Recommendation Systems](RECOMMENDATION_SYSTEMS.md)** - Configure recommendation strategies

#### Understand the System
1. **[Architecture Overview](ARCHITECTURE.md)** - Component design
2. **[System Diagrams](DIAGRAMS.md)** - Visual architecture
3. **[Database & Storage](REDIS_DATABASE_ANALYSIS.md)** - Data layer design
4. **[Redis Integration](RECSYS_REDIS_SUPPORT.md)** - Caching strategy

#### Optimize Performance
1. **[Database & Storage](REDIS_DATABASE_ANALYSIS.md)** - Redis coverage and performance
2. **[Redis Integration](RECSYS_REDIS_SUPPORT.md)** - Caching best practices
3. **[Recommendation Systems](RECOMMENDATION_SYSTEMS.md)** - Performance benchmarks
4. **[Configuration Guide](CONFIG.md)** - Agent archetypes and downcast optimization

#### Extend Functionality
1. **[Extending YSimulator](EXTENDING.md)** - Add new actions and behaviors
2. **[Code Formatting](FORMATTING.md)** - Development standards
3. **[Architecture Overview](ARCHITECTURE.md)** - Component responsibilities

#### Monitor & Debug
1. **[Logging Configuration](LOGGING_CONFIG.md)** - Set up logging
2. **[Server Logging](SERVER_LOGGING.md)** - Analyze server logs
3. **[Action Logging](ACTION_LOGGING.md)** - Track agent actions
4. **[Configuration Guide](CONFIG.md)** - Logging configuration options

#### Work with Features
- **Recommendations**: [Recommendation Systems](RECOMMENDATION_SYSTEMS.md) → [Redis Integration](RECSYS_REDIS_SUPPORT.md)
- **Opinions**: [Opinion Dynamics](OPINION_DYNAMICS.md) → [Configuration Guide](CONFIG.md)
- **Interests**: [Interests & Topics](INTERESTS.md) → [Database & Storage](REDIS_DATABASE_ANALYSIS.md)
- **Annotations**: [Annotations](ANNOTATION_IMPLEMENTATION.md) → [Database & Storage](REDIS_DATABASE_ANALYSIS.md)

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

### Level 2: Core Features
```
CONFIG.md
    ├── Recommendation Systems (RECOMMENDATION_SYSTEMS.md)
    ├── Opinion Dynamics (OPINION_DYNAMICS.md)
    ├── Interests & Topics (INTERESTS.md)
    └── Agent Archetypes & Population

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
- **Primary**: [Recommendation Systems](RECOMMENDATION_SYSTEMS.md)
- **Configuration**: [Configuration Guide](CONFIG.md#content-recommendation-system)
- **Redis Support**: [Redis Integration](RECSYS_REDIS_SUPPORT.md#recommendation-systems)
- **Architecture**: [Architecture Overview](ARCHITECTURE.md#recommendation-systems)
- **Performance**: [Database & Storage](REDIS_DATABASE_ANALYSIS.md)

### Opinion Dynamics
- **Primary**: [Opinion Dynamics](OPINION_DYNAMICS.md)
- **Configuration**: [Configuration Guide](CONFIG.md#opinion-dynamics)
- **Redis Support**: [Redis Integration](RECSYS_REDIS_SUPPORT.md#opinion-dynamics)
- **Architecture**: [Architecture Overview](ARCHITECTURE.md#opinion-dynamics)
- **Examples**: `example/llm_population_100_llm_opinion/`

### Agent Archetypes
- **Primary**: [Configuration Guide](CONFIG.md#agent-archetypes)
- **Architecture**: [Architecture Overview](ARCHITECTURE.md#agent-archetypes)
- **Population File**: [Configuration Guide](CONFIG.md#agent-population-configuration)
- **Downcast Optimization**: [Configuration Guide](CONFIG.md#agent-downcast-feature)

### Interests & Topics
- **Primary**: [Interests & Topics](INTERESTS.md)
- **Configuration**: [Configuration Guide](CONFIG.md#agents-behavior-configuration)
- **Database**: [Database & Storage](REDIS_DATABASE_ANALYSIS.md#topics--interests)
- **Architecture**: [Architecture Overview](ARCHITECTURE.md#interestmanager)

### Redis Integration
- **Primary**: [Redis Integration](RECSYS_REDIS_SUPPORT.md)
- **Analysis**: [Database & Storage](REDIS_DATABASE_ANALYSIS.md)
- **Configuration**: [Configuration Guide](CONFIG.md#redis-configuration)
- **Performance**: [Recommendation Systems](RECOMMENDATION_SYSTEMS.md#redis-vs-sql-backend-comparison)

### Multi-Client Simulations
- **Primary**: [Configuration Guide](CONFIG.md#multi-client-synchronization)
- **Architecture**: [Architecture Overview](ARCHITECTURE.md#coordination-mechanisms)
- **Diagrams**: [System Diagrams](DIAGRAMS.md#multi-client-coordination)

### Logging & Monitoring
- **Configuration**: [Logging Configuration](LOGGING_CONFIG.md)
- **Server Logs**: [Server Logging](SERVER_LOGGING.md)
- **Action Logs**: [Action Logging](ACTION_LOGGING.md)
- **Setup**: [Configuration Guide](CONFIG.md#logging-configuration)

---

## 📊 Documentation Statistics

| Category | Files | Total Lines | Coverage |
|----------|-------|-------------|----------|
| **Getting Started** | 2 | 1,700 | README, Quick Start |
| **Configuration** | 1 | 1,550 | Complete reference |
| **Core Features** | 4 | 3,700 | Recommendations, Opinions, Interests, Annotations |
| **System Design** | 4 | 3,000 | Architecture, Diagrams, Database, Redis |
| **Development** | 2 | 1,000 | Extending, Formatting |
| **Logging** | 3 | 1,000 | Configuration, Server, Actions |
| **Total** | 16 | 11,950 | Comprehensive coverage |

---

## 🚀 Recommended Reading Paths

### Path 1: New User
1. [README](../README.md) - Overview and quick start
2. [Configuration Guide](CONFIG.md) - Set up your simulation
3. [Architecture Overview](ARCHITECTURE.md) - Understand the system
4. [Logging Configuration](LOGGING_CONFIG.md) - Monitor your simulation

### Path 2: Researcher
1. [Architecture Overview](ARCHITECTURE.md) - System design
2. [Recommendation Systems](RECOMMENDATION_SYSTEMS.md) - Algorithms and strategies
3. [Opinion Dynamics](OPINION_DYNAMICS.md) - Models and theory
4. [Database & Storage](REDIS_DATABASE_ANALYSIS.md) - Data structures
5. [Configuration Guide](CONFIG.md) - Experiment configuration

### Path 3: Developer
1. [Architecture Overview](ARCHITECTURE.md) - Component design
2. [System Diagrams](DIAGRAMS.md) - Visual architecture
3. [Extending YSimulator](EXTENDING.md) - Add features
4. [Code Formatting](FORMATTING.md) - Development standards
5. [Database & Storage](REDIS_DATABASE_ANALYSIS.md) - Data layer

### Path 4: Performance Engineer
1. [Database & Storage](REDIS_DATABASE_ANALYSIS.md) - Redis coverage
2. [Redis Integration](RECSYS_REDIS_SUPPORT.md) - Caching strategy
3. [Recommendation Systems](RECOMMENDATION_SYSTEMS.md) - Performance benchmarks
4. [Configuration Guide](CONFIG.md) - Optimization options
5. [Architecture Overview](ARCHITECTURE.md) - System bottlenecks

### Path 5: System Administrator
1. [Configuration Guide](CONFIG.md) - Setup and deployment
2. [Logging Configuration](LOGGING_CONFIG.md) - Monitoring setup
3. [Server Logging](SERVER_LOGGING.md) - Log analysis
4. [Architecture Overview](ARCHITECTURE.md) - System components
5. [Redis Integration](RECSYS_REDIS_SUPPORT.md) - Redis deployment

---

## 🔧 Configuration Files Reference

### Core Configuration
- `server_config.json` → [Configuration Guide](CONFIG.md#server-configuration)
- `simulation_config.json` → [Configuration Guide](CONFIG.md#client-configuration)
- `agent_population.json` → [Configuration Guide](CONFIG.md#agent-population-configuration)
- `llm_prompts.json` → [Configuration Guide](CONFIG.md#llm-prompts-configuration)
- `network.csv` → [Configuration Guide](CONFIG.md#social-network-topology)

### Configuration Examples
- `example/rule_population_100/` → Rule-based agents
- `example/llm_population_100/` → LLM agents with bounded confidence
- `example/llm_population_100_llm_opinion/` → LLM opinion evaluation
- `example/mixed_population_1000/` → Large-scale mixed population

---

## 💡 Key Concepts Index

| Concept | Primary Document | Related Documents |
|---------|------------------|-------------------|
| **Agent Archetypes** | [Configuration Guide](CONFIG.md#agent-archetypes) | [Architecture](ARCHITECTURE.md) |
| **Barriers & Synchronization** | [Architecture Overview](ARCHITECTURE.md#coordination-mechanisms) | [Configuration](CONFIG.md#multi-client-synchronization) |
| **Bounded Confidence** | [Opinion Dynamics](OPINION_DYNAMICS.md#bounded-confidence-model) | [Configuration](CONFIG.md#opinion-dynamics) |
| **Churn & New Agents** | [Configuration Guide](CONFIG.md#agent-population-dynamics) | [Architecture](ARCHITECTURE.md) |
| **Content Recommendations** | [Recommendation Systems](RECOMMENDATION_SYSTEMS.md#content-recommendation-system) | [Redis](RECSYS_REDIS_SUPPORT.md) |
| **Follow Recommendations** | [Recommendation Systems](RECOMMENDATION_SYSTEMS.md#follow-recommendation-system) | [Architecture](ARCHITECTURE.md) |
| **Heartbeat Mechanism** | [Architecture Overview](ARCHITECTURE.md#heartbeat-mechanism) | [Configuration](CONFIG.md#multi-client-synchronization) |
| **Interests & Attention** | [Interests & Topics](INTERESTS.md) | [Database](REDIS_DATABASE_ANALYSIS.md) |
| **LLM Integration** | [Configuration Guide](CONFIG.md#llm-configuration) | [Architecture](ARCHITECTURE.md#llm-service) |
| **Opinion Groups** | [Opinion Dynamics](OPINION_DYNAMICS.md#opinion-groups) | [Configuration](CONFIG.md) |
| **Redis Caching** | [Redis Integration](RECSYS_REDIS_SUPPORT.md) | [Database](REDIS_DATABASE_ANALYSIS.md) |
| **Sliding Windows** | [Redis Integration](RECSYS_REDIS_SUPPORT.md#sliding-window) | [Interests](INTERESTS.md) |

---

## 📝 Missing Documentation

Based on analysis of the codebase and existing documentation, the following areas could benefit from additional documentation:

### Potential Additions
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

- **Start Here**: [README](../README.md)
- **Configuration Questions**: [Configuration Guide](CONFIG.md)
- **Technical Questions**: [Architecture Overview](ARCHITECTURE.md)
- **Development Questions**: [Extending YSimulator](EXTENDING.md)
- **Performance Questions**: [Database & Storage](REDIS_DATABASE_ANALYSIS.md)

---

**Last Updated:** January 1, 2026  
**Documentation Version:** 2.0  
**YSimulator Version:** 2.0
