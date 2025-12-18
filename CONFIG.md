# Configuration Guide

This guide explains the JSON configuration files used by YSimulator.

## Quick Start

### Running the Server

```bash
python run_server.py --config path/to/server_config.json
```

### Running the Client

```bash
python run_client.py --config path/to/simulation_config.json
```

Example configurations are provided in the `example_conf/` directory.

## Configuration Files

### 1. `server_config.json` - Server Configuration

Controls the Ray server parameters:

```json
{
  "server_name": "orchestrator_server",  // Name for this server instance
  "namespace": "social_sim",              // Ray namespace for the cluster
  "address": "auto",                      // "auto" for local, or specific address
  "port": null,                           // Port number (null for default)
  "database_file": "simulation.db",       // SQLite database filename
  "min_to_start": 1                       // Minimum clients before simulation starts
}
```

**Parameters:**
- `server_name`: Unique name for this server instance (used in logs)
- `namespace`: The Ray namespace used for actor isolation
- `address`: Server address ("auto" for automatic local setup, or a specific address)
- `port`: Reserved for future use. Ray port is currently managed through Ray's internal mechanisms or environment variables
- `database_file`: Path to the SQLite database file (relative to config directory)
- `min_to_start`: Minimum number of connected clients before simulation begins (default: 1)

**Note**: The database file and logs are created in the same directory as the configuration file.

### 2. `agent_population.json` - Agent Population Configuration

Defines the agent population with detailed profiles based on the User_mgmt model:

```json
{
  "agents": [
    {
      "id": 1,
      "username": "validator_001",
      "email": "validator001@simulation.local",
      "age": 35,
      "oe": "medium",
      "co": "high",
      "ex": "low",
      "ag": "medium",
      "ne": "low",
      "education_level": "graduate",
      "gender": "non-binary",
      "nationality": "US",
      "profession": "Data Analyst",
      "activity_profile": "Evening Active",
      "archetype": "Validator",
      "cluster": 0,
      "llm": true
    }
  ],
  "generation_config": {
    "num_additional_agents": 47,
    "cluster_distribution": {
      "weights": [0.4, 0.3, 0.3]
    },
    "llm_enabled_probability": 0.1
  }
}
```

**Agent Fields** (based on User_mgmt model):
- `id`: Unique agent identifier (required)
- `username`: Agent username (required)
- `email`: Agent email address
- `age`: Age in years
- **Big Five Personality Traits**:
  - `oe`: Openness to Experience (low/medium/high)
  - `co`: Conscientiousness (low/medium/high)
  - `ex`: Extraversion (low/medium/high)
  - `ag`: Agreeableness (low/medium/high)
  - `ne`: Neuroticism (low/medium/high)
- `education_level`: Education level (high_school/college/graduate/phd)
- `gender`: Gender identity (male/female/non-binary)
- `nationality`: Nationality code (US/UK/CA/AU/EU)
- `profession`: Job title or profession
- `activity_profile`: Activity pattern (Always On/Morning Active/Evening Active/Weekend Warrior)
- `archetype`: Social media archetype (Validator/Broadcaster/Explorer)
- `cluster`: Behavioral cluster (0=Validator, 1=Broadcaster, 2=Explorer)
- `llm`: Whether to use LLM for this agent (true/false)
- `daily_activity_level`: Activity frequency (1-4)
- `toxicity`: Toxicity setting (yes/no)
- `leaning`: Political leaning (neutral/left/right)
- `language`: Language code (en/es/fr/de)

**Generation Config**:
- `num_additional_agents`: Number of agents to generate automatically
- `cluster_distribution.weights`: Distribution weights for clusters [0, 1, 2]
- `llm_enabled_probability`: Probability that generated agents use LLM
- `age_range`: Min and max age for generated agents [min, max]
- `default_settings`: Default values for generated agents

**Notes**:
- Predefined agents in the `agents` array are created first
- Additional agents are generated using the `generation_config` settings
- All agents are registered in the `user_mgmt` database table at simulation start
- Existing agents (by ID) are not re-registered

### 3. `simulation_config.json` - Simulation Configuration

Main configuration for client simulation parameters:

```json
{
  "client_name": "client_1",         // Name for this client instance
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
- `client_name`: Unique name for this client instance (used in logs, not from command line)
- `namespace`: Ray namespace (must match server)
- `server.address`: Server address (null to use ray_config.temp file)
- `server.port`: Server port (null for default)
- `llm.address`: LLM server address (e.g., "localhost" for Ollama)
- `llm.port`: LLM server port (e.g., 11434 for Ollama)
- `llm.model`: LLM model name (e.g., "llama3.2")
- `llm.temperature`: LLM temperature for generation (0.0-1.0)
- `simulation.num_days`: Number of days to simulate (0 = infinite, continues until manually stopped)
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

## Logging

Both server and client generate rotating JSON logs in the `logs/` directory (created in the same location as the configuration file).

### Log Files

- **Server logs**: `logs/{server_name}_server.log` - Main server process
- **Server actor logs**: `logs/{server_name}_actor.log` - Orchestrator actor
- **Client logs**: `logs/{client_name}_client.log` - Main client process
- **Client actor logs**: `logs/{client_name}_actor.log` - Simulation actor

### Log Format

Logs are in JSON format with the following structure:

```json
{
  "timestamp": "2025-12-18T10:47:47.123Z",
  "level": "INFO",
  "message": "Agent registration complete",
  "module": "server",
  "function": "register_agents",
  "line": 150,
  "registered": 50,
  "skipped": 0,
  "execution_time_ms": 125.5
}
```

### Log Rotation

- Maximum log file size: 10MB
- Number of backup files: 5
- Old logs are automatically rotated to `.log.1`, `.log.2`, etc.

## Code Formatting

This project uses automatic code formatting with:
- **black**: Code formatter
- **isort**: Import sorter

A pre-commit hook automatically formats Python files before each commit. Install formatting tools:

```bash
pip install black isort
```

The formatting is enforced automatically on commit.

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
  "agents": [...],
  "generation_config": {
    "num_additional_agents": 200
  }
}
```

### Example 3: Add Custom Agent with Specific Personality

Edit `agent_population.json`:
```json
{
  "agents": [
    {
      "id": 1,
      "username": "critical_thinker",
      "age": 45,
      "oe": "high",
      "co": "high",
      "ex": "low",
      "ag": "medium",
      "ne": "low",
      "education_level": "phd",
      "profession": "Professor",
      "archetype": "Validator",
      "cluster": 0,
      "llm": true
    }
  ]
}
```

### Example 4: Run for Limited Time

Edit `simulation_config.json`:
```json
{
  "simulation": {
    "num_days": 7,
    "num_slots_per_day": 24
  }
}
```

### Example 5: Use Different LLM Model

Edit `simulation_config.json`:
```json
{
  "llm": {
    "model": "llama3.1",
    "temperature": 0.8
  }
}
```

### Example 6: Customize Personas

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
