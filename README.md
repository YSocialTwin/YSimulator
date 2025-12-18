# YSimulator

A distributed social media simulation system using Ray for orchestration and LLM-based agent behaviors.

## Features

- **Distributed Architecture**: Server-client model using Ray for scalable simulation
- **Configurable Parameters**: JSON-based configuration for all simulation parameters
- **LLM Integration**: Support for Ollama-based language models for realistic agent behaviors
- **Agent Diversity**: Three agent clusters with different behavioral patterns
- **Flexible Simulation**: Configurable duration, agent population, and LLM parameters
- **Structured Logging**: JSON logs with timestamps and execution times

## Configuration

The simulator uses JSON configuration files stored in a single directory. See [CONFIG.md](CONFIG.md) for detailed documentation.

### Configuration Files

All configuration files are kept in the same directory:

- `server_config.json` - Server parameters (name, namespace, address, port, database)
- `simulation_config.json` - Client parameters, LLM settings, simulation duration
- `agent_population.json` - Agent profiles and distribution
- `llm_prompts.json` - LLM prompt templates and personas

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

See [CONFIG.md](CONFIG.md) for full configuration options and examples.