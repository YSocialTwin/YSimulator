# YSimulator Documentation

Welcome to the **YSimulator** documentation! YSimulator is a distributed social media simulation system using Ray for orchestration and LLM-based agent behaviors.

## What is YSimulator?

YSimulator is a powerful simulation framework designed to model social media dynamics with realistic agent behaviors powered by Large Language Models (LLMs). It provides researchers and developers with a flexible platform to study social network phenomena, opinion dynamics, and information spread.

## Key Features

- **Distributed Architecture**: Server-client model using Ray for scalable simulation
- **Multi-Database Support**: SQLite, PostgreSQL, MySQL backends with optional Redis caching
- **Configurable Parameters**: JSON-based configuration for all simulation parameters
- **LLM Integration**: Support for Ollama and vLLM backends for realistic agent behaviors with batch inference
- **Agent Profiles**: User-based agent system with Big Five personality traits
- **Opinion Dynamics**: Configurable models including bounded confidence and LLM-based evaluation for realistic opinion evolution and polarization
- **Multi-Client Synchronization**: Robust barrier-based coordination with heartbeat liveness detection
- **Client-Side Step Management**: Clients independently manage their simulation timelines
- **Stress/Reward Feedback**: Optional stress/reward aggregation with dynamic churn driven by directed interactions
- **Reciprocal Network Dynamics**: Follow-back and unfollow-back decisions, including secondary follow actions
- **Flexible Simulation**: Configurable duration, agent population, and LLM parameters
- **Structured Logging**: Rotating JSON logs with timestamps and execution times
- **UUID-Based IDs**: Universal identifiers for distributed compatibility
- **Performance Optimization**: vLLM backend support for 8-30x faster LLM inference through batch processing

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Initialize Database (Optional)

If using PostgreSQL or MySQL, initialize the database schema:

```bash
python scripts/init_db.py --config my_config
```

### Run the Simulation

1. **Prepare Configuration**

```bash
# Copy example configuration to a directory
mkdir my_config
cp example_conf/*.json my_config/

# Edit as needed
nano my_config/server_config.json
```

2. **Start the Server**

```bash
python run_server.py --config my_config
```

3. **Start Client(s)**

```bash
python run_client.py --config my_config
```

You can start multiple clients to distribute the simulation load.

## Documentation Structure

This documentation is organized into several sections:

### 🚀 Getting Started
Start here if you're new to YSimulator. Learn about installation, configuration, and running your first simulation.

### ⚙️ Configuration
Complete guides to all configuration options, including server setup, simulation parameters, and advanced features like vLLM integration.

### 🏗️ Architecture
Deep dives into the system design, including the distributed architecture, coordination mechanisms, and component interactions.

### ✨ Features
Detailed documentation of major features including recommendation systems, opinion dynamics, interest management, and vLLM batch inference.

### 🤖 Agent System
Learn about the agent-based modeling system, including agent types, actions, and temporal activity patterns.

### 💾 Data Storage
Understand the hybrid SQL/Redis storage architecture and caching strategies.

### 👨‍💻 Development
Guides for extending YSimulator, adding new agent actions, customizing behaviors, and contributing to the project.

### 📊 Logging
Configure and use the structured logging system to monitor and analyze simulations.

### 🔬 Analysis & Performance
Performance optimization strategies, bottleneck analysis, and profiling guides.

### 🧪 Testing
Information about the test suite and coverage reports.

## Quick Links

### For Researchers
- [Getting Started Guide](getting-started/INDEX.md)
- [Configuration Guide](configuration/CONFIG.md)
- [Opinion Dynamics](features/OPINION_DYNAMICS.md)
- [Social Feedback & Reciprocal Follows](features/SOCIAL_FEEDBACK_AND_RECIPROCAL_FOLLOWS.md)
- [Agent Types](agents/AGENT_TYPES.md)

### For Developers
- [Architecture Overview](architecture/ARCHITECTURE.md)
- [Extending YSimulator](development/EXTENDING.md)
- [System Diagrams](architecture/DIAGRAMS.md)
- [Code Formatting](development/FORMATTING.md)

### For System Administrators
- [Configuration Guide](configuration/CONFIG.md)
- [vLLM Integration](configuration/VLLM_INTEGRATION_GUIDE.md)
- [Logging Configuration](logging/LOGGING_CONFIG.md)
- [Performance Optimization](analysis/BOTTLENECK_ANALYSIS_SUMMARY.md)

## Community & Support

- **GitHub Repository**: [YSocialTwin/YSimulator](https://github.com/YSocialTwin/YSimulator)
- **Issues**: Report bugs or request features on [GitHub Issues](https://github.com/YSocialTwin/YSimulator/issues)

## License

See the repository for license information.

---

!!! tip "Navigation"
    Use the sidebar to navigate through different sections of the documentation. Each section contains detailed guides and reference materials.
