# Configuration Guide

This guide explains the JSON configuration files used by YSimulator.

## Quick Start

### Running the Server

```bash
python run_server.py --config path/to/config_directory
```

The configuration directory must contain `server_config.json`.

### Running the Client

```bash
python run_client.py --config path/to/config_directory
```

The configuration directory must contain:
- `simulation_config.json`
- `agent_population.json`
- `llm_prompts.json`

### Default Behavior

If no `--config` argument is provided, both server and client will look for configuration files in the current directory.

Example configurations are provided in the `example_conf/` directory:

```bash
# Run server with example config
python run_server.py --config example_conf

# Run client with example config
python run_client.py --config example_conf
```

## File Structure

All configuration files, database, and logs are kept in the same directory:

```
config_directory/
├── server_config.json          # Server configuration
├── simulation_config.json      # Client simulation configuration
├── agent_population.json       # Agent profiles
├── llm_prompts.json           # LLM prompts and personas
├── simulation.db              # Database (auto-created)
├── ray_config.temp            # Ray address (auto-created)
└── logs/                      # Log files (auto-created)
    ├── {server_name}_server.log
    ├── {server_name}_actor.log
    ├── {client_name}_client.log
    └── {client_name}_actor.log
```

## Configuration Files

### 1. `server_config.json` - Server Configuration

Controls the Ray server parameters and database backend:

```json
{
  "server_name": "orchestrator_server",  // Name for this server instance
  "namespace": "social_sim",              // Ray namespace for the cluster
  "address": "auto",                      // "auto" for local, or specific address
  "port": null,                           // Port number (null for default)
  "database": {                           // Database configuration
    "type": "sqlite",                     // Database type: sqlite, postgresql, or mysql
    "sqlite": {                           // SQLite-specific configuration
      "filename": "simulation.db"         // Database filename (created in config directory)
    },
    "postgresql": {                       // PostgreSQL-specific configuration
      "host": "localhost",                // PostgreSQL server host
      "port": 5432,                       // PostgreSQL server port
      "database": "ysimulator",           // Database name
      "username": "postgres",             // Database username
      "password": "password"              // Database password
    },
    "mysql": {                            // MySQL-specific configuration
      "host": "localhost",                // MySQL server host
      "port": 3306,                       // MySQL server port
      "database": "ysimulator",           // Database name
      "username": "root",                 // Database username
      "password": "password"              // Database password
    }
  },
  "min_to_start": 1,                      // Minimum clients before simulation starts
  "redis": {                              // Redis configuration (optional)
    "enabled": false,                     // Set to true to use Redis
    "host": "localhost",                  // Redis server host
    "port": 6379,                         // Redis server port
    "db": 0,                              // Redis database number
    "password": null,                     // Redis password (null if no auth)
    "sliding_window_days": 2              // Days of data to keep in Redis cache
  }
}
```

**Parameters:**
- `server_name`: Unique name for this server instance (used in logs)
- `namespace`: The Ray namespace used for actor isolation
- `address`: Server address ("auto" for automatic local setup, or a specific address)
- `port`: Reserved for future use. Ray port is currently managed through Ray's internal mechanisms or environment variables
- `database`: Database configuration object
  - `type`: Database backend type - `"sqlite"`, `"postgresql"`, or `"mysql"`
  - `sqlite`: SQLite-specific settings (used when type is "sqlite")
    - `filename`: Database filename (stored in config directory)
  - `postgresql`: PostgreSQL-specific settings (used when type is "postgresql")
    - `host`: PostgreSQL server hostname or IP address
    - `port`: PostgreSQL server port (default: 5432)
    - `database`: Database name (required)
    - `username`: Database username (required)
    - `password`: Database password (optional, can be null for trusted connections)
  - `mysql`: MySQL-specific settings (used when type is "mysql")
    - `host`: MySQL server hostname or IP address
    - `port`: MySQL server port (default: 3306)
    - `database`: Database name (required)
    - `username`: Database username (required)
    - `password`: Database password (optional, can be null for trusted connections)
- `min_to_start`: Minimum number of connected clients before simulation begins (default: 1)
- `redis`: Redis configuration object (optional)
  - `enabled`: Set to `true` to use Redis, `false` to use SQL database only (default: false)
  - `host`: Redis server hostname or IP address (required if enabled)
  - `port`: Redis server port number  
  - `db`: Redis database number (0-15)
  - `password`: Redis authentication password (set to `null` if no password required)
  - `sliding_window_days`: Number of simulation days to keep in Redis cache (default: 2)

**Database Backend:**

The server supports three SQL database backends via SQLAlchemy:

1. **SQLite** (default): 
   - File-based database stored in the configuration directory
   - No additional setup required
   - Best for: Single-machine deployments, development, testing
   - Connection string: `sqlite:///path/to/simulation.db`

2. **PostgreSQL**:
   - Robust, production-ready database server
   - Requires PostgreSQL server to be running and accessible
   - Best for: Production deployments, multi-client simulations, concurrent access
   - Requires Python package: `pip install psycopg2-binary`
   - Connection string: `postgresql://username:password@host:port/database`

3. **MySQL**:
   - Popular open-source database server
   - Requires MySQL server to be running and accessible
   - Best for: Production deployments with existing MySQL infrastructure
   - Requires Python package: `pip install pymysql`
   - Connection string: `mysql+pymysql://username:password@host:port/database`

**Choosing a Database:**
- **SQLite**: Simple file-based storage, no server needed. Good for development and single-machine deployments.
- **PostgreSQL**: Enterprise-grade features, excellent for production with high concurrency and complex queries.
- **MySQL**: Wide adoption, good performance, excellent for production with existing MySQL infrastructure.

**Database Setup:**
For PostgreSQL or MySQL, you must:
1. Install and run the database server
2. Create the database: `CREATE DATABASE ysimulator;`
3. Create a user with appropriate permissions
4. Install the required Python driver (psycopg2-binary for PostgreSQL, pymysql for MySQL)
5. Configure the connection details in `server_config.json`

The database tables will be automatically created by SQLAlchemy when the server starts.

**Example Configurations:**
The `example_conf/` directory provides example server configurations for each database type:
- `server_config.json` - Default SQLite configuration
- `server_config.postgresql.json` - PostgreSQL configuration example
- `server_config.mysql.json` - MySQL configuration example

To use a specific database type, copy the appropriate example file to your configuration directory and rename it to `server_config.json`, then update the connection parameters.

The server supports two database backends:
- **SQL Database** (SQLite/PostgreSQL/MySQL): Persistent storage for all simulation data
- **Redis** (optional): In-memory cache for better performance with sliding window

**Redis Sliding Window:**
When Redis is enabled, the system maintains a sliding window of recent data in Redis for fast access:
- At the end of each simulation day, all data is consolidated to the SQL database for persistence
- Data older than `sliding_window_days` is removed from Redis to manage memory
- Recent data (within the sliding window) remains in Redis for fast queries
- Example: With `sliding_window_days: 2`, Redis keeps the current day and previous day's data

This approach provides:
- **Fast access** to recent data via Redis
- **Long-term persistence** of all data in SQL database
- **Memory efficiency** by automatically pruning old data from Redis
- **Data safety** with everything backed up to SQL database

**ID System:**
- **User IDs**: Integer values from configuration (agent profiles)
- **Post IDs**: UUIDs (universally unique identifiers) for cross-system compatibility
- **Interaction IDs**: UUIDs for global uniqueness

If Redis connection fails or is disabled, the system automatically uses the SQL database for all operations.

**Note**: For SQLite, the database file is created in the same directory as the configuration file. For PostgreSQL and MySQL, the database must already exist on the server.

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

To use YSimulator with a custom configuration directory:

1. **Create a configuration directory** with all required files:
   ```bash
   mkdir my_simulation
   cp example_conf/*.json my_simulation/
   ```

2. **Edit configurations** as needed:
   ```bash
   nano my_simulation/server_config.json
   nano my_simulation/simulation_config.json
   ```

3. **Run the server** pointing to the directory:
   ```bash
   python run_server.py --config my_simulation
   ```

4. **Run the client** in another terminal:
   ```bash
   python run_client.py --config my_simulation
   ```

All generated files (database, logs, temporary files) will be created in the same configuration directory.

### Default Configuration

If no `--config` argument is provided, the server and client will look for configuration files in the current directory:

```bash
# Server looks for ./server_config.json
python run_server.py

# Client looks for ./simulation_config.json, ./agent_population.json, ./llm_prompts.json
python run_client.py
```

### Customizing Configuration

1. Edit the JSON files in your configuration directory
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
