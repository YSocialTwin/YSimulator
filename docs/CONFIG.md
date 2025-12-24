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
├── server_config.json                    # Server configuration
├── simulation_config.json                # Client simulation configuration
├── agent_population.json                 # Agent profiles (generic)
├── {client_name}_agent_population.json   # Client-specific agent profiles (optional)
├── llm_prompts.json                      # LLM prompts and personas (generic)
├── {client_name}_llm_prompts.json        # Client-specific LLM prompts (optional)
├── network.csv                           # Social network topology (generic, optional)
├── {client_name}_network.csv             # Client-specific network (optional)
├── simulation.db                         # Database (auto-created)
├── ray_config.temp                       # Ray address (auto-created)
└── logs/                                 # Log files (auto-created)
    ├── {server_name}_server.log
    ├── {server_name}_actor.log
    ├── {client_name}_client.log
    └── {client_name}_actor.log
```

## Client-Specific Configuration

Clients can use client-specific configuration files by prefixing the file name with `{client_name}_`. The client name is defined in `simulation_config.json` under the `client_name` field.

When a client starts, it will:
1. Load `simulation_config.json` to get the client name
2. Look for `{client_name}_agent_population.json`, `{client_name}_llm_prompts.json`, and `{client_name}_network.csv`
3. Fall back to generic files (`agent_population.json`, `llm_prompts.json`, `network.csv`) if client-specific files don't exist

This allows multiple clients to run with different configurations in multi-client scenarios.

**Example:**

For a client named "client_1":
- `client_1_agent_population.json` - Client-specific agent profiles
- `client_1_llm_prompts.json` - Client-specific LLM prompts
- `client_1_network.csv` - Client-specific social network

If these files don't exist, the client will use the generic files.

## Dynamic Social Network Features

YSimulator includes advanced social network features that allow agents to form and break relationships during simulation:

### 1. Dynamic Follow Actions

Agents can discover and follow other users during simulation using recommendation algorithms. This is configured per-agent using the `frecsys_type` field in agent profiles.

**Available Recommendation Strategies:**

- `random`: Random user selection from non-following users
- `common_neighbors`: Friend-of-friend recommendations (users with mutual connections)
- `jaccard`: Jaccard similarity of follow sets
- `adamic_adar`: Adamic/Adar index scoring (weighted by common neighbor connectivity)
- `preferential_attachment`: Popular users with many followers (rich-get-richer)

**Implementation Details:**

- Server uses efficient query-based approaches (no in-memory graph construction)
- SQL backend: JOIN queries, subqueries, and aggregations
- Redis backend: Key-value operations with minimal iterations
- Supports political leaning bias for homophily
- Follow action available to Explorer archetype by default

**Agent Configuration:**

In `agent_population.json`, specify the follow recommendation strategy:

```json
{
  "id": 1,
  "username": "explorer_001",
  "archetype": "Explorer",
  "frecsys_type": "common_neighbors"
}
```

If not specified, defaults to `"random"`.

### 2. Daily Follow Evaluation

At the end of each simulation day, agents that were active during the day can establish new follow relationships. This is controlled by the `probability_of_daily_follow` configuration parameter.

**Configuration:**

In `simulation_config.json`, add under the `agents` section:

```json
{
  "agents": {
    "probability_of_daily_follow": 0.1
  }
}
```

**Behavior:**

At the end of each day (last time slot), for each agent that was active during the day:

- With probability `daily_follow`, the agent evaluates new follow candidates
- Uses the agent's `frecsys_type` recommendation strategy to get top-10 suggestions
- Randomly selects one candidate from suggestions to follow
- Creates a FOLLOW action in the Follow table

**Implementation:**

- Tracks all agents active during each simulation day
- Evaluates daily follows at transition to next day (slot 23 → day+1)
- Uses agent-specific follow recommendation strategies
- No political leaning bias applied (neutral selection)
- Independent of other follow mechanisms (action-based, secondary)

**Use Cases:**

- Model gradual network growth over time
- Simulate daily social discovery behaviors
- Create realistic follow patterns independent of content
- Study long-term network evolution

### 3. Secondary Follow Behavior

After reading or commenting on posts, agents can establish or break social ties with content authors. This is controlled by the `probability_of_secondary_follow` configuration parameter.

**Configuration:**

In `simulation_config.json`, add under the `agents` section:

```json
{
  "agents": {
    "probability_of_secondary_follow": 0.3
  }
}
```

**Behavior:**

With probability `secondary_follow`, after a read or comment action:

- **Rule-based agents**: Randomly decide to follow, unfollow, or make no change (equal probabilities)
- **LLM agents**: Heuristic decision based on current follow status:
  - If not following: 30% chance to follow the author
  - If already following: 10% chance to unfollow the author
  - Otherwise: No change

**Implementation:**

- Tracks all read/comment interactions with post authors
- Evaluates secondary follow after main action pipeline completes
- Checks current follow status before making decision
- Creates FOLLOW or UNFOLLOW actions in Follow table
- Both actions include round timestamp for temporal analysis

**Use Cases:**

- Model organic network growth through content interactions
- Simulate unfollowing based on content disagreement
- Create realistic social network evolution
- Study relationship formation patterns

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
  "timeout_seconds": 60,                  // Seconds before considering a client stale (default: 60)
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
- `timeout_seconds`: Seconds before considering a client stale/inactive and automatically removing it to prevent deadlocks (default: 60)
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
- `recsys_type`: Content recommendation strategy (random/rchrono/rchrono_popularity/rchrono_followers/etc.)
- `frecsys_type`: Follow recommendation strategy (random/common_neighbors/jaccard/adamic_adar/preferential_attachment)

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
  "llm_v": {
    "address": "localhost",
    "port": 11434,
    "model": "minicpm-v",
    "temperature": 0.5
  },
  "simulation": {
    "num_days": 0,
    "num_slots_per_day": 24
  },
  "agents": {
    "reading_from_follower_ratio": 0.6,
    "max_length_thread_reading": 5,
    "attention_window": 336,
    "probability_of_daily_follow": 0.0,
    "probability_of_secondary_follow": 0.0,
    "actions_likelihood": {
      "post": 0.3,
      "image": 0.1,
      "like": 0.2,
      "comment": 0.15,
      "share": 0.1
    }
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
- `llm_v.address`: **Vision LLM** server address (optional, for image description)
- `llm_v.port`: **Vision LLM** server port (optional)
- `llm_v.model`: **Vision LLM** model name (e.g., "minicpm-v" for image understanding)
- `llm_v.temperature`: **Vision LLM** temperature for generation (0.0-1.0)
- `simulation.num_days`: Number of days to simulate (0 = infinite, continues until manually stopped)
- `simulation.num_slots_per_day`: Time slots per day (typically 24)
- `agents.probability_of_daily_follow`: Probability (0.0-1.0) of evaluating new follows at end of each day for active agents (default: 0.0)
- `agents.probability_of_secondary_follow`: Probability (0.0-1.0) of evaluating follow/unfollow after read/comment actions (default: 0.0)
- `agents.actions_likelihood`: **Action probabilities** - Dictionary mapping action types to their likelihood (optional)

**Agent Behavior Configuration:**

The `agents` section controls agent behavior parameters:

```json
{
  "agents": {
    "reading_from_follower_ratio": 0.6,
    "max_length_thread_reading": 5,
    "attention_window": 336,
    "probability_of_daily_follow": 0.0,
    "probability_of_secondary_follow": 0.0,
    "actions_likelihood": {
      "post": 0.3,
      "image": 0.1,
      "like": 0.2,
      "comment": 0.15,
      "share": 0.1
    }
  }
}
```

- `reading_from_follower_ratio`: Proportion of posts from followed users in recommendations (0.0-1.0)
- `max_length_thread_reading`: Maximum comment thread depth to read
- `attention_window`: Time slots of content visibility (default: 336 = 14 days × 24 slots)
- `probability_of_daily_follow`: Probability of evaluating new follows at end of each day for active agents (0.0-1.0, default: 0.0)
- `probability_of_secondary_follow`: Probability of follow/unfollow evaluation after content interactions (0.0-1.0, default: 0.0)
- `actions_likelihood`: Dictionary of action types and their relative probabilities (optional)
  - `post`: Create a new post
  - `image`: Share an image with commentary (requires llm_v configuration and images in database)
  - `like`: React to a post
  - `comment`: Comment on a post
  - `share`: Share a post

**Vision LLM Configuration (llm_v):**

The `llm_v` section configures a vision-capable language model for image understanding:

- **Purpose**: Describes images extracted from RSS feeds and generates image commentary
- **Requirements**: A vision-capable LLM like minicpm-v running on Ollama
- **Optional**: If not configured, image extraction will be skipped
- **Image Action**: Requires llm_v to be configured for agents to share images

**Action Likelihood System:**

The `actions_likelihood` dictionary allows fine-grained control over agent behavior:

- **Values**: Relative probabilities (not required to sum to 1.0)
- **Optional**: If not provided, default probabilities are used
- **Image Action**: Requires:
  - `llm_v` configuration in simulation_config.json
  - Images in the database (extracted from RSS feeds by page agents)
  - `describe_image` and `generate_image_commentary` prompts in llm_prompts.json

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
  },
  "describe_image": {
    "system_template": "You are an AI assistant that describes images accurately and concisely.",
    "user_template": "Describe the following image. Write in English. <img {url}>"
  },
  "generate_image_commentary": {
    "system_template": "{persona} Your toxicity level is {toxicity}.",
    "user_template": "Create a social media post about this image: {image_description}. {topics_instruction} Max 280 characters."
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
- `describe_image.system_template`: System prompt for vision LLM image description
- `describe_image.user_template`: User prompt template for image description
  - Available variables: `{url}` - Image URL
- `generate_image_commentary.system_template`: System prompt for image post generation
  - Available variables: `{persona}`, `{toxicity}`
- `generate_image_commentary.user_template`: User prompt for creating image posts
  - Available variables: `{image_description}`, `{topics_instruction}`

**Image-Related Prompts:**

The `describe_image` prompt is used by the vision LLM (llm_v) to generate descriptions of images extracted from RSS feeds:
- **Input**: Image URL from RSS feed entry
- **Output**: Text description stored in the images table
- **Requirements**: llm_v configuration with a vision-capable model (e.g., minicpm-v)

The `generate_image_commentary` prompt creates social media posts for the image sharing action:
- **Input**: Image description, agent persona, agent toxicity level, and related topics
- **Output**: Social media post text (max 280 characters)
- **Usage**: LLM agents use this to create personalized commentary when sharing images
- **Rule-based agents**: Share images with the text "IMAGE" instead of using this prompt

### 5. `network.csv` - Social Network Topology (Optional)

Defines the initial social network structure by specifying follow relationships between agents.

**Format:**

Each row in the CSV represents a directed edge (follow relationship):
```csv
follower_username,user_username
```

Where:
- `follower_username`: Username of the agent who follows
- `user_username`: Username of the agent being followed

**Example:**

```csv
validator_001,TechNewsPage
broadcaster_001,TechNewsPage
explorer_001,TechNewsPage
validator_001,broadcaster_001
broadcaster_001,explorer_001
explorer_001,validator_001
```

This creates a network where:
- All three agents follow TechNewsPage
- validator_001 follows broadcaster_001
- broadcaster_001 follows explorer_001
- explorer_001 follows validator_001

**Behavior:**

1. **Automatic Loading**: If `network.csv` (or `{client_name}_network.csv`) exists in the configuration directory, it is automatically loaded when the client connects.

2. **Client-Specific Files**: The client first looks for `{client_name}_network.csv`. If not found, it falls back to `network.csv`. This allows different clients to have different social networks.

3. **Multi-Client Safe**: The system checks if any edges from the CSV already exist in the database before loading. This ensures the network is only loaded once, even in multi-client scenarios.

4. **Agent Validation**: Only edges between agents defined in `agent_population.json` (or `{client_name}_agent_population.json`) are created. Invalid usernames are logged and skipped.

5. **Database Storage**: Follow relationships are stored in the `follow` table with:
   - `action`: Set to "follow"
   - `round`: Empty string (initial network has no associated simulation round)

6. **Recommendation Systems**: Once loaded, the network influences content recommendation systems like `rchrono_followers` which prioritize posts from followed users.

**Notes:**

- The file is optional. If not present, agents start with no follow relationships.
- Client-specific files (e.g., `client_1_network.csv`) take precedence over generic files.
- Usernames must exactly match those in `agent_population.json` (case-sensitive).
- The CSV should not have a header row.
- Empty lines are ignored.
- Follow relationships can still be created dynamically during simulation through agent actions.

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

## Multi-Client Synchronization

The server implements robust synchronization mechanisms to handle multiple concurrent clients with different simulation durations and potential failures.

### How It Works

1. **Barrier Synchronization**: The server waits for all **active** clients to submit their actions before advancing the simulation slot
2. **Graceful Completion**: When a client finishes its planned activities, it notifies the server and no longer blocks progression
3. **Heartbeat Mechanism**: Clients send periodic heartbeats (every 5 seconds) to signal they're alive
4. **Timeout Detection**: If a client doesn't send a heartbeat for `timeout_seconds` (default: 60s), it's automatically removed

### Client States

- **Active**: Registered and still participating in simulation
- **Completed**: Finished all planned activities, notified server, no longer blocks others
- **Stale**: Haven't sent heartbeat within timeout period, automatically removed

### Heartbeat-Based Liveness Detection

The system uses **heartbeat-only** detection to determine if clients are alive:

- **Processing Time Doesn't Matter**: Even if a client takes hours to process a slot (e.g., due to many agents or slow LLM), it won't be marked as stale as long as heartbeats arrive
- **Heartbeat Interval**: Clients send heartbeats every `heartbeat_interval` seconds (configurable in `simulation_config.json`, default: 5s)
- **Timeout Detection**: Only clients that **stop sending heartbeats** for more than `timeout_seconds` are marked as stale
- **Recommendation**: Set `timeout_seconds` to at least 10-12x the `heartbeat_interval` to account for network delays

Example: If `heartbeat_interval = 5` and `timeout_seconds = 60`, a client processing a slot for 10 minutes is fine as long as it sends heartbeats every 5 seconds. Only if heartbeats stop arriving for 60 seconds will it be considered stale.

### Client-Side Simulation Step Management

**Design Philosophy**: The client handles its own simulation progression, while the server provides coordination.

**Registration Flow:**
1. Client registers with server, specifying `num_days` (informational only)
2. Server responds with current `start_day` and `start_slot` as the starting point
3. Client tracks progress locally from this starting point
4. Client exits when `current_day >= start_day + num_days`

**On Client Restart:**
- Client re-registers and receives the **current server time** as new starting point
- Client runs for its full configured duration from that new starting point
- **Example**: 
  - Server at day 10
  - Client joins with `num_days = 3`
  - Server returns: `start_day = 10, start_slot = 5`
  - Client tracks: will run while `current_day < 10 + 3` (i.e., days 10, 11, 12)
  - Client exits when server advances to day 13
  - If client restarts when server is at day 20:
    - Server returns: `start_day = 20, start_slot = 1`
    - Client runs days 20-23 (full 3-day duration from new start)

**Benefits:**
- Simpler server logic - no per-client completion state tracking
- Client autonomy - each client manages its own simulation timeline
- Easier to understand - day counting happens where simulation runs
- Better separation of concerns - server coordinates, client simulates

### Example Scenario

```
Initial: 3 clients start (A, B, C) at Day 1
Day 1 Slot 1: A, B, C all submit → Server advances to Slot 2
Day 1 Slot 2: A, B, C all submit → Server advances to Day 2 Slot 1
...
Day 5: Client A reaches its personal max (started day 1, num_days=5)
  → A exits its simulation loop
  → A calls complete_client()
  → Server marks A as "completed"
  → Only B and C now block advancement
Day 6-7: B and C continue without waiting for A
Day 7: Client B reaches its max
  → B exits and calls complete_client()
  → Only C now blocks advancement
Day 8: New Client D joins (server at day 8, configured for 3 days)
  → D receives start_day=8 from server
  → D will run until day 11 (local check: day < 8 + 3)
  → D participates alongside C
Day 10: Client C finishes, only D active
Day 11: Client D finishes (day 11 >= 8 + 3)
  → Simulation complete
```

### Handling Crashed Clients

If Client B crashes on Day 6 without notifying the server:
1. Client B stops sending heartbeats
2. After 60 seconds (timeout_seconds), server detects B is stale
3. Server automatically marks B as completed
4. Clients C and D continue without being blocked

Note: The crashed client's processing time is irrelevant. Even if it was legitimately processing for 10 minutes, as long as heartbeats arrived, it wouldn't be marked as stale.

### Configuration

**Server Configuration** (`server_config.json`):
```json
{
  "timeout_seconds": 60  // Time without heartbeat before marking client as stale
}
```

**Client Configuration** (`simulation_config.json`):
```json
{
  "simulation": {
    "heartbeat_interval": 5  // Seconds between heartbeat signals
  }
}
```

**Recommendations:**
- **heartbeat_interval**: 3-10 seconds (lower = faster failure detection, higher = less network overhead)
- **timeout_seconds**: 10-12x heartbeat_interval minimum
  - Example: heartbeat_interval=5s → timeout_seconds=60s minimum
- **High-latency networks**: Increase both values proportionally
- **Development/debugging**: Set timeout_seconds to 300-600s to avoid interruptions

### Best Practices

1. **Varied Simulation Durations**: Clients can have different `num_days` settings
2. **Dynamic Joining**: New clients can join mid-simulation and run for their full duration
3. **Restart Behavior**: Restarting a client doesn't cause immediate completion - it runs for full duration from current server time
4. **Graceful Shutdown**: Always let the client run() method complete to ensure proper cleanup
5. **Monitor Logs**: Check for timeout warnings indicating clients that stopped sending heartbeats
6. **Adjust Timeouts**: If you see false stale detections, increase `timeout_seconds` or decrease `heartbeat_interval`
