# YSimulator

> Runs large-scale simulations in a distributed way on HPC clusters.

## Overview

YSimulator is a distributed social media simulation system that uses [Ray](https://www.ray.io/) for orchestration and LLM-based agent behaviours. It is the HPC simulator of [YSocial](https://github.com/YSocialTwin/YSocial). In [YSocial](https://github.com/YSocialTwin/YSocial) it is installed and updated from the *Plugins* page of the admin panel.

It uses a distributed coordinator-worker pattern:

- **Server (Orchestrator)**: coordinates temporal progression and manages barriers
- **Clients (Workers)**: execute simulation steps independently
- **Database Middleware**: abstracts storage (SQL + optional Redis)
- **Ray**: enables distributed execution without manual networking

For component diagrams and data flow, see [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) and [docs/architecture/DIAGRAMS.md](docs/architecture/DIAGRAMS.md).

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

## Requirements

- Python 3 and the dependencies in `requirements.txt` (Ray included)
- An LLM backend: Ollama or vLLM
- A database: SQLite (default), PostgreSQL or MySQL, with optional Redis caching

## Installation

```bash
git clone https://github.com/YSocialTwin/YSimulator.git
cd YSimulator
pip install -r requirements.txt
```

If you use PostgreSQL or MySQL, initialise the database schema:

```bash
python scripts/init_db.py --config my_config
```

## Usage

### 1. Prepare Configuration

```bash
# Copy example configuration to a directory
mkdir my_config
cp example/<scenario>/*.json my_config/

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

### Output files

All output files are created in the configuration directory:

- `simulation.db` - SQLite database with simulation data
- `logs/` - Rotating JSON logs for server and client
- `ray_config.temp` - Temporary Ray cluster address file (auto-created by server, used by clients)

## Configuration

The simulator uses JSON configuration files stored in a single directory. See [docs/configuration/CONFIG.md](docs/configuration/CONFIG.md) for the complete documentation.

All configuration files are kept in the same directory:

- `server_config.json` - Server parameters (name, namespace, address, port, database)
- `simulation_config.json` - Client parameters, LLM settings, simulation duration
- `agent_population.json` - Agent profiles and distribution
- `llm_prompts.json` - LLM prompt templates and personas
- `network.csv` - (Optional) Initial social network topology defining follow relationships

Edit the files to customise the number of agents and their characteristics, the LLM model and parameters, the simulation duration, the agent personas and behaviours, and the database location.

## Project structure

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

## Documentation

**[Online documentation](https://ysocialtwin.github.io/YSimulator/)** (GitHub Pages, with search) and the [documentation index](docs/getting-started/INDEX.md), organised by topic and by use case.

### Quick links

**Getting Started:**
- **[Configuration Guide](docs/configuration/CONFIG.md)** - Complete guide to all configuration options
- **[Architecture Overview](docs/architecture/ARCHITECTURE.md)** - System design and components

**Core Features:**
- **[Recommendation Systems](docs/features/RECOMMENDATION_SYSTEMS.md)** - Content & follow recommendations with 15 algorithms
- **[Opinion Dynamics](docs/features/OPINION_DYNAMICS.md)** - Bounded confidence and LLM evaluation models
- **[Interests & Topics](docs/features/INTERESTS.md)** - Interest management with attention windows

**Agent System:**
- **[Agent Actions](docs/agents/AGENT_ACTIONS.md)** - All available agent actions
- **[Agent Types](docs/agents/AGENT_TYPES.md)** - Agent types and archetypes
- **[Agent Temporal Activities](docs/agents/AGENT_TEMPORAL_ACTIVITIES.md)** - Temporal patterns and dynamics

**System & Performance:**
- **[vLLM Integration Guide](docs/configuration/VLLM_INTEGRATION_GUIDE.md)** - High-performance LLM backend with batch inference (8x-30x speedup)
- **[vLLM Batch Inference](docs/features/VLLM_BATCH_INFERENCE.md)** - Comprehensive batch inference implementation (10x-50x speedup)
- **[Database & Storage](docs/data-storage/REDIS_COVERAGE_ANALYSIS.md)** - Redis/SQL hybrid architecture and Redis coverage
- **[Redis Integration](docs/data-storage/REDIS_RECOMMENDATION_SYSTEMS.md)** - Caching strategies for the recommendation systems
- **[Performance Optimization](docs/analysis/BOTTLENECK_ANALYSIS_SUMMARY.md)** - Bottleneck analysis and optimization strategies

**Development:**
- **[Extension Guide](docs/development/EXTENDING.md)** - How to add new agent actions and features
- **[System Diagrams](docs/architecture/DIAGRAMS.md)** - Visual architecture and interaction diagrams
- **[Code Formatting](docs/development/FORMATTING.md)** - Development guidelines and tooling

**Monitoring:**
- **[Logging Configuration](docs/logging/LOGGING_CONFIG.md)** - Comprehensive logging setup
- **[Server Logging](docs/logging/SERVER_LOGGING.md)** - Server log analysis
- **[Action Logging](docs/logging/ACTION_LOGGING.md)** - Client action tracking

**Browse by Use Case**: See the [Documentation Index](docs/getting-started/INDEX.md) for recommended reading paths by role (Researcher, Developer, Admin) and feature cross-references.

## Testing

Run the test suite:

```bash
# Run all tests
python -m pytest YSimulator/tests/

# Run specific test file
python -m pytest YSimulator/tests/test_network_loading.py

# Run tests with better isolation (recommended for avoiding test interference)
# Install pytest-xdist first: pip install pytest-xdist
python -m pytest YSimulator/tests/ -n auto

# Run tests in parallel with 4 workers
python -m pytest YSimulator/tests/ -n 4
```

**Note:** Some tests use module-level mocking (e.g., `test_server.py` mocks `ray.remote`). When running the full test suite, use `pytest-xdist` with the `-n` flag to run tests in separate worker processes, which prevents mock interference between test modules.

## Contributing

Contributions are welcome. Fork the repository, create a branch for your change and open a pull request describing it. Code contributions should follow the formatting guidelines in [docs/development/FORMATTING.md](docs/development/FORMATTING.md).

### Development setup

1. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

2. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```

The pre-commit hooks will automatically run `black`, `isort`, and `flake8` on every commit to ensure code quality and consistency.

### Extending YSimulator

To add new agent actions or customize behavior:

1. Define the data model (SQLAlchemy)
2. Add storage methods to DatabaseMiddleware
3. Create server handler method
4. Implement client-side action logic
5. Integrate into the action loop

See [docs/development/EXTENDING.md](docs/development/EXTENDING.md) for step-by-step instructions and examples.

### Utilities

The `scripts/` directory contains utility scripts:

- **init_db.py**: Initialize database schema for PostgreSQL/MySQL
- **convert_ids_to_uuid.py**: Migrate existing data to UUID format
- **validate_network_loading.py**: Validate network topology files
- **postgresql_server.sql**: PostgreSQL database schema

## Citation

If you use YSocial in your research, please cite:

```bibtex
@article{rossetti2024ysocial,
  title={Y Social: an LLM-powered microblogging Digital Twin},
  author={Rossetti, Giulio and Stella, Massimo and Cazabet, Rémy and
  Abramski, Katherine and Cau, Erica and Citraro, Salvatore and
  Failla, Andrea and Improta, Riccardo and Morini, Virginia and
  Pansanella, Virginia},
  year={2024}
}
```

## License

Released under the GNU General Public License v3.0. See [LICENSE](LICENSE) for details.
