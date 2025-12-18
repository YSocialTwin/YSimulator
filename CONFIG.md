# Configuration Guide

This guide explains the JSON configuration files used by YSimulator.

## Configuration Files

### 1. `server_config.json` - Server Configuration

Controls the Ray server parameters:

```json
{
  "namespace": "social_sim",      // Ray namespace for the cluster
  "address": "auto",               // "auto" for local, or specific address
  "port": null,                    // Port number (null for default)
  "database_file": "simulation.db" // SQLite database filename
}
```

**Parameters:**
- `namespace`: The Ray namespace used for actor isolation
- `address`: Server address ("auto" for automatic local setup, or a specific address)
- `port`: Port for Ray server (null uses default)
- `database_file`: Path to the SQLite database file

### 2. `agent_population.json` - Agent Population Configuration

Defines the agent population characteristics:

```json
{
  "num_agents": 50,
  "cluster_distribution": {
    "weights": [0.4, 0.3, 0.3],
    "llm_enabled_probability": 0.1
  }
}
```

**Parameters:**
- `num_agents`: Total number of agents per client
- `cluster_distribution.weights`: Distribution weights for clusters [0, 1, 2]
  - Cluster 0: Validators (skeptical, brief)
  - Cluster 1: Broadcasters (high energy, viral)
  - Cluster 2: Explorers (curious, questioning)
- `cluster_distribution.llm_enabled_probability`: Probability that an agent uses LLM vs rule-based behavior

### 3. `simulation_config.json` - Simulation Configuration

Main configuration for client simulation parameters:

```json
{
  "namespace": "social_sim",
  "server": {
    "address": null,
    "port": null
  },
  "llm": {
    "address": "localhost",
    "port": 11434,
    "model": "llama3.2",
    "temperature": 0.7
  },
  "simulation": {
    "num_days": 0,
    "num_slots_per_day": 24
  }
}
```

**Parameters:**
- `namespace`: Ray namespace (must match server)
- `server.address`: Server address (null to use ray_config.temp file)
- `server.port`: Server port (null for default)
- `llm.address`: LLM server address (e.g., "localhost" for Ollama)
- `llm.port`: LLM server port (e.g., 11434 for Ollama)
- `llm.model`: LLM model name (e.g., "llama3.2")
- `llm.temperature`: LLM temperature for generation (0.0-1.0)
- `simulation.num_days`: Number of days to simulate (0 = infinite)
- `simulation.num_slots_per_day`: Time slots per day (typically 24)

### 4. `llm_prompts.json` - LLM Prompt Templates

Defines personas and prompt templates for LLM interactions:

```json
{
  "personas": {
    "0": "You are a 'Validator'. Skeptical, brief, authentic.",
    "1": "You are a 'Broadcaster'. High energy, viral, controversial.",
    "2": "You are an 'Explorer'. Curious, asking questions."
  },
  "generate_post": {
    "system_template": "{persona}",
    "user_template": "Write a tweet for Day {day} Slot {slot}. Max 15 words."
  },
  "decide_reaction": {
    "system_template": "You are user type {cluster_id}. Read post. Reply ONLY: 'LIKE', 'COMMENT', 'IGNORE'.",
    "user_template": "{post_content}"
  }
}
```

**Parameters:**
- `personas`: Dictionary mapping cluster IDs to persona descriptions
- `generate_post.system_template`: System prompt template for post generation
  - Available variables: `{persona}`
- `generate_post.user_template`: User prompt template for post generation
  - Available variables: `{day}`, `{slot}`
- `decide_reaction.system_template`: System prompt template for reaction decisions
  - Available variables: `{cluster_id}`
- `decide_reaction.user_template`: User prompt template for reaction decisions
  - Available variables: `{post_content}`

## Usage

### Starting the Server

```bash
python run_server.py
```

The server will read `server_config.json` and start with the specified configuration.

### Starting the Client

```bash
python run_client.py --id client_1
```

The client will read:
- `simulation_config.json` - for simulation and LLM parameters
- `agent_population.json` - for agent population settings
- `llm_prompts.json` - for LLM prompt templates

### Customizing Configuration

1. Edit the JSON files to customize parameters
2. No code changes required
3. Restart server/client to apply changes

## Examples

### Example 1: Change Database Location

Edit `server_config.json`:
```json
{
  "database_file": "/data/my_simulation.db"
}
```

### Example 2: Increase Agent Population

Edit `agent_population.json`:
```json
{
  "num_agents": 100
}
```

### Example 3: Run for Limited Time

Edit `simulation_config.json`:
```json
{
  "simulation": {
    "num_days": 7,
    "num_slots_per_day": 24
  }
}
```

### Example 4: Use Different LLM Model

Edit `simulation_config.json`:
```json
{
  "llm": {
    "model": "llama3.1",
    "temperature": 0.8
  }
}
```

### Example 5: Customize Personas

Edit `llm_prompts.json`:
```json
{
  "personas": {
    "0": "You are a critical thinker who questions everything.",
    "1": "You are an enthusiastic content creator.",
    "2": "You are a curious researcher."
  }
}
```
