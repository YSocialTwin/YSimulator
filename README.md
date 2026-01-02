# YSimulator

A distributed social media simulation system using Ray for orchestration and LLM-based agent behaviors.

## Features

- **Distributed Architecture**: Server-client model using Ray for scalable simulation
- **Multi-Database Support**: SQLite, PostgreSQL, MySQL backends with optional Redis caching
- **Configurable Parameters**: JSON-based configuration for all simulation parameters
- **LLM Integration**: Support for Ollama-based language models for realistic agent behaviors
- **Agent Profiles**: User_mgmt-based agent system with Big Five personality traits
- **Opinion Dynamics**: Configurable models including bounded confidence and LLM-based evaluation for realistic opinion evolution and polarization
- **Multi-Client Synchronization**: Robust barrier-based coordination with heartbeat liveness detection
- **Client-Side Step Management**: Clients independently manage their simulation timelines
- **Flexible Simulation**: Configurable duration, agent population, and LLM parameters
- **Structured Logging**: Rotating JSON logs with timestamps and execution times
- **UUID-Based IDs**: Universal identifiers for distributed compatibility

## Documentation

**📚 [Complete Documentation Index](docs/INDEX.md)** - Navigate all documentation organized by topic and use case

### Quick Links

**Getting Started:**
- **[Configuration Guide](docs/CONFIG.md)** - Complete guide to all configuration options (1,550 lines)
- **[Architecture Overview](docs/ARCHITECTURE.md)** - System design and components (800 lines)

**Core Features:**
- **[Recommendation Systems](docs/RECOMMENDATION_SYSTEMS.md)** - Content & follow recommendations with 15 algorithms (1,200 lines)
- **[Opinion Dynamics](docs/OPINION_DYNAMICS.md)** - Bounded confidence and LLM evaluation models (1,200 lines)
- **[Interests & Topics](docs/INTERESTS.md)** - Interest management with attention windows (300 lines)

**System & Performance:**
- **[Database & Storage](docs/REDIS_DATABASE_ANALYSIS.md)** - Redis/SQL hybrid architecture, 89% Redis coverage (480 lines)
- **[Redis Integration](docs/RECSYS_REDIS_SUPPORT.md)** - Caching strategies and implementation (870 lines)

**Development:**
- **[Extension Guide](docs/EXTENDING.md)** - How to add new agent actions and features (950 lines)
- **[System Diagrams](docs/DIAGRAMS.md)** - Visual architecture and interaction diagrams (800 lines)
- **[Code Formatting](docs/FORMATTING.md)** - Development guidelines and tooling

**Monitoring:**
- **[Logging Configuration](docs/LOGGING_CONFIG.md)** - Comprehensive logging setup (420 lines)
- **[Server Logging](docs/SERVER_LOGGING.md)** - Server log analysis (380 lines)
- **[Action Logging](docs/ACTION_LOGGING.md)** - Client action tracking (160 lines)

**Browse by Use Case**: See the [Documentation Index](docs/INDEX.md) for recommended reading paths by role (Researcher, Developer, Admin) and feature cross-references.

## Configuration

The simulator uses JSON configuration files stored in a single directory. See [docs/CONFIG.md](docs/CONFIG.md) for detailed documentation.

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

See [docs/CONFIG.md](docs/CONFIG.md) for full configuration options and examples.

## Architecture

YSimulator uses a distributed coordinator-worker pattern:

- **Server (Orchestrator)**: Coordinates temporal progression and manages barriers
- **Clients (Workers)**: Execute simulation steps independently
- **Database Middleware**: Abstracts storage (SQL + optional Redis)
- **Ray**: Enables distributed execution without manual networking

For detailed architecture information, including component diagrams and data flow, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/DIAGRAMS.md](docs/DIAGRAMS.md).

## Extending YSimulator

To add new agent actions or customize behavior:

1. Define the data model (SQLAlchemy)
2. Add storage methods to DatabaseMiddleware
3. Create server handler method
4. Implement client-side action logic
5. Integrate into the action loop

See [docs/EXTENDING.md](docs/EXTENDING.md) for step-by-step instructions and examples.

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

Code contributions should follow the formatting guidelines in [docs/FORMATTING.md](docs/FORMATTING.md). Pre-commit hooks automatically enforce `black` and `isort` formatting.