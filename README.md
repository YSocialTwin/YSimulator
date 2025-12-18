# YSimulator

A distributed social media simulation system using Ray for orchestration and LLM-based agent behaviors.

## Features

- **Distributed Architecture**: Server-client model using Ray for scalable simulation
- **Configurable Parameters**: JSON-based configuration for all simulation parameters
- **LLM Integration**: Support for Ollama-based language models for realistic agent behaviors
- **Agent Diversity**: Three agent clusters with different behavioral patterns
- **Flexible Simulation**: Configurable duration, agent population, and LLM parameters

## Configuration

The simulator uses JSON configuration files for all parameters. See [CONFIG.md](CONFIG.md) for detailed documentation.

### Configuration Files

- `server_config.json` - Server parameters (namespace, address, port, database)
- `agent_population.json` - Agent population and distribution
- `simulation_config.json` - Simulation parameters, LLM settings, duration
- `llm_prompts.json` - LLM prompt templates and personas

## Quick Start

### 1. Start the Server

```bash
python run_server.py
```

### 2. Start Client(s)

```bash
python run_client.py --id client_1
```

You can start multiple clients to distribute the simulation load.

## Customization

Edit the JSON configuration files to customize:
- Number of agents
- LLM model and parameters
- Simulation duration
- Agent personas and behaviors
- Database location

See [CONFIG.md](CONFIG.md) for full configuration options and examples.