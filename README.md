# YSimulator

A distributed social media simulation system using Ray for orchestration and LLM-based agent behaviors.

## Features

- **Distributed Architecture**: Server-client model using Ray for scalable simulation
- **Multi-Database Support**: SQLite, PostgreSQL, MySQL backends with optional Redis caching
- **Configurable Parameters**: JSON-based configuration for all simulation parameters
- **LLM Integration**: Support for Ollama and vLLM backends for realistic agent behaviors with batch inference
- **Agent Profiles**: User_mgmt-based agent system with Big Five personality traits
- **Opinion Dynamics**: Configurable models including bounded confidence and LLM-based evaluation for realistic opinion evolution and polarization
- **Multi-Client Synchronization**: Robust barrier-based coordination with heartbeat liveness detection
- **Client-Side Step Management**: Clients independently manage their simulation timelines
- **Flexible Simulation**: Configurable duration, agent population, and LLM parameters
- **Structured Logging**: Rotating JSON logs with timestamps and execution times
- **UUID-Based IDs**: Universal identifiers for distributed compatibility
- **Performance Optimization**: vLLM backend support for 8-30x faster LLM inference through batch processing

## Documentation

**📚 [Complete Documentation Index](docs/getting-started/INDEX.md)** - Navigate all documentation organized by topic and use case

> **New in 2.1**: Documentation has been reorganized into thematic subdirectories for better navigation and discoverability.

### Quick Links

**Getting Started:**
- **[Configuration Guide](docs/configuration/CONFIG.md)** - Complete guide to all configuration options (1,550 lines)
- **[Architecture Overview](docs/architecture/ARCHITECTURE.md)** - System design and components (960+ lines)

**Core Features:**
- **[Recommendation Systems](docs/features/RECOMMENDATION_SYSTEMS.md)** - Content & follow recommendations with 15 algorithms (1,200 lines)
- **[Opinion Dynamics](docs/features/OPINION_DYNAMICS.md)** - Bounded confidence and LLM evaluation models (1,200 lines)
- **[Interests & Topics](docs/features/INTERESTS.md)** - Interest management with attention windows (300 lines)

**Agent System:**
- **[Agent Actions](docs/agents/AGENT_ACTIONS.md)** - All available agent actions (700+ lines)
- **[Agent Types](docs/agents/AGENT_TYPES.md)** - Agent types and archetypes (670+ lines)
- **[Agent Temporal Activities](docs/agents/AGENT_TEMPORAL_ACTIVITIES.md)** - Temporal patterns and dynamics (990+ lines)

**System & Performance:**
- **[vLLM Integration Guide](docs/configuration/VLLM_INTEGRATION_GUIDE.md)** - High-performance LLM backend with batch inference (8x-30x speedup)
- **[vLLM Batch Inference](docs/features/VLLM_BATCH_INFERENCE.md)** - Comprehensive batch inference implementation (10x-50x speedup)
- **[Database & Storage](docs/data-storage/REDIS_DATABASE_ANALYSIS.md)** - Redis/SQL hybrid architecture, 89% Redis coverage (480 lines)
- **[Redis Integration](docs/data-storage/RECSYS_REDIS_SUPPORT.md)** - Caching strategies and implementation (870 lines)
- **[Performance Optimization](docs/analysis/BOTTLENECK_ANALYSIS_SUMMARY.md)** - Bottleneck analysis and optimization strategies

**Development:**
- **[Extension Guide](docs/development/EXTENDING.md)** - How to add new agent actions and features (1,210+ lines)
- **[System Diagrams](docs/architecture/DIAGRAMS.md)** - Visual architecture and interaction diagrams (800 lines)
- **[Code Formatting](docs/development/FORMATTING.md)** - Development guidelines and tooling

**Monitoring:**
- **[Logging Configuration](docs/logging/LOGGING_CONFIG.md)** - Comprehensive logging setup (420 lines)
- **[Server Logging](docs/logging/SERVER_LOGGING.md)** - Server log analysis (380 lines)
- **[Action Logging](docs/logging/ACTION_LOGGING.md)** - Client action tracking (160 lines)

**Browse by Use Case**: See the [Documentation Index](docs/getting-started/INDEX.md) for recommended reading paths by role (Researcher, Developer, Admin) and feature cross-references.

## Configuration

The simulator uses JSON configuration files stored in a single directory. See [docs/configuration/CONFIG.md](docs/configuration/CONFIG.md) for detailed documentation.

### Configuration Files

All configuration files are kept in the same directory:

- `server_config.json` - Server parameters (name, namespace, address, port, database)
- `simulation_config.json` - Client parameters, LLM settings, simulation duration
- `agent_population.json` - Agent profiles and distribution
- `llm_prompts.json` - LLM prompt templates and personas
- `network.csv` - (Optional) Initial social network topology defining follow relationships

## Installation

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Initialize Database (Optional)

If using PostgreSQL or MySQL, initialize the database schema:

```bash
python scripts/init_db.py --config my_config
```

## Quick Start

### 1. Prepare Configuration

```bash
# Copy example configuration to a directory
mkdir my_config
cp example_conf/*.json my_config/

# Edit as needed
nano my_config/server_config.json
```

### 2. Start the Server

```bash
python run_server.py --config my_config
```

### 3. Start Client(s)

```bash
python run_client.py --config my_config
```

You can start multiple clients to distribute the simulation load.

### Default Configuration

If `--config` is not specified, both server and client will use the current directory:

```bash
# Uses ./server_config.json
python run_server.py

# Uses ./simulation_config.json, ./agent_population.json, ./llm_prompts.json
python run_client.py
```

## Output Files

All output files are created in the configuration directory:

- `simulation.db` - SQLite database with simulation data
- `logs/` - Rotating JSON logs for server and client
- `ray_config.temp` - Temporary Ray cluster address file

## Customization

Edit the JSON configuration files to customize:
- Number of agents and their characteristics
- LLM model and parameters
- Simulation duration
- Agent personas and behaviors
- Database location

See [docs/configuration/CONFIG.md](docs/configuration/CONFIG.md) for full configuration options and examples.

## Architecture

YSimulator uses a distributed coordinator-worker pattern:

- **Server (Orchestrator)**: Coordinates temporal progression and manages barriers
- **Clients (Workers)**: Execute simulation steps independently
- **Database Middleware**: Abstracts storage (SQL + optional Redis)
- **Ray**: Enables distributed execution without manual networking

For detailed architecture information, including component diagrams and data flow, see [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) and [docs/architecture/DIAGRAMS.md](docs/architecture/DIAGRAMS.md).

## Extending YSimulator

To add new agent actions or customize behavior:

1. Define the data model (SQLAlchemy)
2. Add storage methods to DatabaseMiddleware
3. Create server handler method
4. Implement client-side action logic
5. Integrate into the action loop

See [docs/development/EXTENDING.md](docs/development/EXTENDING.md) for step-by-step instructions and examples.

## Project Structure

```
YSimulator/
├── YSimulator/          # Main package
│   ├── YServer/        # Server orchestration logic
│   ├── YClient/        # Client agent logic
│   └── tests/          # Unit and integration tests
├── scripts/            # Utility scripts
│   ├── init_db.py              # Database initialization
│   ├── convert_ids_to_uuid.py  # ID migration utility
│   ├── validate_network_loading.py  # Network validation
│   └── postgresql_server.sql   # PostgreSQL schema
├── docs/               # Documentation
├── example/            # Example configurations
├── run_server.py       # Server entry point
├── run_client.py       # Client entry point
└── requirements.txt    # Python dependencies
```

## Testing

Run the test suite:

```bash
# Run all tests
python -m pytest YSimulator/tests/

# Run specific test file
python -m pytest YSimulator/tests/test_network_loading.py
```

## Utilities

The `scripts/` directory contains utility scripts:

- **init_db.py**: Initialize database schema for PostgreSQL/MySQL
- **convert_ids_to_uuid.py**: Migrate existing data to UUID format
- **validate_network_loading.py**: Validate network topology files
- **postgresql_server.sql**: PostgreSQL database schema

## Contributing

Code contributions should follow the formatting guidelines in [docs/development/FORMATTING.md](docs/development/FORMATTING.md).

### Development Setup

1. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

2. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```

The pre-commit hooks will automatically run `black`, `isort`, and `flake8` on every commit to ensure code quality and consistency.