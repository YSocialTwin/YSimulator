# YSimulator Configuration Guide

## Introduction

This guide explains how to configure YSimulator through JSON configuration files. YSimulator is designed to be highly customizable without requiring code changes - all simulation parameters, agent behaviors, and system settings are controlled through configuration files.

### What You'll Learn

- How to structure your configuration directory
- What each configuration file controls
- How to customize simulation behavior
- Advanced features like multi-client synchronization, agent churn, and dynamic network formation

### Quick Navigation

- [Getting Started](#getting-started) - Run your first simulation
- [Configuration Files](#configuration-files-overview) - Overview of all config files
- [Server Configuration](#server-configuration) - Database, Ray, and server settings
- [Client Configuration](#client-configuration) - Simulation and agent behavior
- [Advanced Features](#advanced-features) - Churn, new agents, archetypes, and network dynamics
- [Multi-Client Setup](#multi-client-synchronization) - Running distributed simulations
- [Logging](#logging-configuration) - Log files and rotation

---

## Getting Started

### Quick Start

1. **Run the server:**
```bash
python run_server.py --config path/to/config_directory
```

2. **Run the client** (in another terminal):
```bash
python run_client.py --config path/to/config_directory
```

### Default Behavior

If no `--config` argument is provided, both server and client look for configuration files in the current directory.

### Example Configurations

Example configurations are provided in the `example/` directory:

```bash
# Run with rule-based population
python run_server.py --config example/rule_population_100
python run_client.py --config example/rule_population_100

# Run with mixed population
python run_server.py --config example/mixed_population_1000
python run_client.py --config example/mixed_population_1000
```

---

## Configuration Directory Structure

All configuration files, database, and logs are kept in the same directory:

```
config_directory/
├── server_config.json                    # Server configuration (required for server)
├── simulation_config.json                # Client simulation configuration (required for client)
├── agent_population.json                 # Agent profiles (required for client)
├── llm_prompts.json                      # LLM prompts and personas (required for client)
├── network.csv                           # Social network topology (optional)
├── {client_name}_agent_population.json   # Client-specific agent profiles (optional)
├── {client_name}_llm_prompts.json        # Client-specific LLM prompts (optional)
├── {client_name}_network.csv             # Client-specific network (optional)
├── simulation.db                         # Database (auto-created)
├── ray_config.temp                       # Ray address (auto-created)
└── logs/                                 # Log files (auto-created)
    ├── _server.log                       # Server request log
    ├── {server_name}_server.log          # Server execution log
    ├── {server_name}_actor.log           # Server actor log
    ├── {client_name}_execution.log       # Client execution log
    ├── {client_id}_actor.log             # Client actor log
    └── {client_id}_client.log            # Client action log
```

### Client-Specific Configuration

Clients can use client-specific configuration files by prefixing the file name with `{client_name}_`. The client name is defined in `simulation_config.json` under the `client_name` field.

**Resolution order:**
1. Load `simulation_config.json` to get the client name
2. Look for `{client_name}_agent_population.json`, `{client_name}_llm_prompts.json`, and `{client_name}_network.csv`
3. Fall back to generic files if client-specific files don't exist

This enables multiple clients with different configurations in multi-client scenarios.

---

## Configuration Files Overview

YSimulator uses five main configuration files:

| File | Purpose | Required By | Can Be Client-Specific |
|------|---------|-------------|------------------------|
| `server_config.json` | Server, database, Ray settings | Server | No |
| `simulation_config.json` | Simulation parameters, agent behavior | Client | No |
| `agent_population.json` | Agent profiles and generation | Client | Yes |
| `llm_prompts.json` | LLM personas and prompt templates | Client | Yes |
| `network.csv` | Initial social network topology | Client | Yes (optional) |

---

## Server Configuration

### File: `server_config.json`

Controls Ray server parameters, database backend, and server behavior.

#### Complete Example

```json
{
  "server_name": "orchestrator_server",
  "namespace": "social_sim",
  "address": "auto",
  "port": null,
  "database": {
    "type": "sqlite",
    "sqlite": {
      "filename": "simulation.db"
    },
    "postgresql": {
      "host": "localhost",
      "port": 5432,
      "database": "ysimulator",
      "username": "postgres",
      "password": "password"
    },
    "mysql": {
      "host": "localhost",
      "port": 3306,
      "database": "ysimulator",
      "username": "root",
      "password": "password"
    }
  },
  "min_to_start": 1,
  "timeout_seconds": 60,
  "redis": {
    "enabled": false,
    "host": "localhost",
    "port": 6379,
    "db": 0,
    "password": null,
    "sliding_window_days": 2
  },
  "posts": {
    "visibility_rounds": 36
  },
  "simulation": {
    "agent_archetypes": {
      "enabled": true,
      "distribution": {
        "validator": 0.33,
        "broadcaster": 0.33,
        "explorer": 0.34
      },
      "transitions": {
        "validator": {"validator": 0.85, "broadcaster": 0.1, "explorer": 0.05},
        "broadcaster": {"validator": 0.1, "broadcaster": 0.8, "explorer": 0.1},
        "explorer": {"validator": 0.05, "broadcaster": 0.1, "explorer": 0.85}
      }
    }
  },
  "logging": {
    "enable_server_log": true,
    "enable_actor_log": true,
    "enable_request_log": true,
    "enable_console_log": true
  }
}
```

#### Core Parameters

**Basic Settings:**
- `server_name` (string): Unique name for this server instance (used in logs)
- `namespace` (string): Ray namespace for actor isolation (must match client)
- `address` (string): Server address ("auto" for automatic local setup)
- `port` (number|null): Reserved for future use

**Synchronization:**
- `min_to_start` (number, default: 1): Minimum clients before simulation begins
- `timeout_seconds` (number, default: 60): Seconds before marking client as stale

**Content Visibility:**
- `posts.visibility_rounds` (number, default: 36): Time slots posts remain visible

#### Database Configuration

YSimulator supports three SQL database backends via SQLAlchemy:

**1. SQLite (Default)**
```json
{
  "database": {
    "type": "sqlite",
    "sqlite": {
      "filename": "simulation.db"
    }
  }
}
```
- **Best for**: Development, testing, single-machine deployments
- **Setup**: No additional setup required
- **Connection**: `sqlite:///path/to/simulation.db`

**2. PostgreSQL**
```json
{
  "database": {
    "type": "postgresql",
    "postgresql": {
      "host": "localhost",
      "port": 5432,
      "database": "ysimulator",
      "username": "postgres",
      "password": "password"
    }
  }
}
```
- **Best for**: Production, multi-client, concurrent access
- **Setup**: Install PostgreSQL, create database, install `psycopg2-binary`
- **Connection**: `postgresql://username:password@host:port/database`

**3. MySQL**
```json
{
  "database": {
    "type": "mysql",
    "mysql": {
      "host": "localhost",
      "port": 3306,
      "database": "ysimulator",
      "username": "root",
      "password": "password"
    }
  }
}
```
- **Best for**: Production with existing MySQL infrastructure
- **Setup**: Install MySQL, create database, install `pymysql`
- **Connection**: `mysql+pymysql://username:password@host:port/database`

**Database Setup Steps:**
1. Install and run the database server (PostgreSQL/MySQL)
2. Create the database: `CREATE DATABASE ysimulator;`
3. Create a user with appropriate permissions
4. Install the required Python driver
5. Configure connection details in `server_config.json`

Database tables are automatically created by SQLAlchemy when the server starts.

#### Redis Configuration

Redis provides an optional in-memory cache with sliding window for better performance:

```json
{
  "redis": {
    "enabled": true,
    "host": "localhost",
    "port": 6379,
    "db": 0,
    "password": null,
    "sliding_window_days": 2
  }
}
```

**Parameters:**
- `enabled` (boolean): Enable Redis caching
- `host` (string): Redis server hostname
- `port` (number): Redis server port
- `db` (number): Redis database number (0-15)
- `password` (string|null): Authentication password
- `sliding_window_days` (number): Days of data to keep in Redis

**How It Works:**
- Recent data (within sliding window) stays in Redis for fast access
- At end of each day, data is consolidated to SQL for persistence
- Old data automatically pruned from Redis to manage memory
- If Redis fails, system automatically falls back to SQL

**Benefits:**
- Fast access to recent data
- Long-term persistence in SQL
- Memory efficiency through automatic pruning
- Data safety with SQL backup

#### Logging Configuration

Control which log files are generated. See [LOGGING_CONFIG.md](../logging/LOGGING_CONFIG.md) for details.

```json
{
  "logging": {
    "enable_server_log": true,
    "enable_actor_log": true,
    "enable_request_log": true,
    "enable_console_log": true
  }
}
```

---

## Client Configuration

### File: `simulation_config.json`

Controls simulation parameters, agent behavior, and LLM settings.

#### Complete Example

```json
{
  "client_name": "client_1",
  "namespace": "social_sim",
  "server": {
    "address": null,
    "port": null
  },
  "llm": {
    "address": "localhost",
    "port": 11434,
    "model": "llama3.2",
    "temperature": 0.7,
    "llm_api_key": "NULL",
    "llm_max_tokens": -1
  },
  "llm_v": {
    "address": "localhost",
    "port": 11434,
    "model": "minicpm-v",
    "temperature": 0.5,
    "llm_api_key": "NULL",
    "llm_max_tokens": 300
  },
  "simulation": {
    "num_days": 0,
    "num_slots_per_day": 24,
    "heartbeat_interval": 5,
    "percentage_new_agents_iteration": 0.0,
    "percentage_removed_agents_iteration": 0.0,
    "discussion_topics": ["war", "politics", "sport", "books", "movies"],
    "activity_profiles": {
      "Always On": "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23",
      "Morning Active": "6,7,8,9,10,11,12",
      "Evening Active": "17,18,19,20,21,22,23",
      "Weekend Warrior": "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23"
    },
    "hourly_activity": {
      "0": 0.023, "1": 0.021, "2": 0.02, "3": 0.02,
      "4": 0.018, "5": 0.017, "6": 0.017, "7": 0.018,
      "8": 0.02, "9": 0.02, "10": 0.021, "11": 0.022,
      "12": 0.024, "13": 0.027, "14": 0.03, "15": 0.032,
      "16": 0.032, "17": 0.032, "18": 0.032, "19": 0.031,
      "20": 0.03, "21": 0.029, "22": 0.027, "23": 0.025
    },
    "actions_likelihood": {
      "post": 3.0,
      "image": 0.0,
      "news": 0.0,
      "comment": 5.0,
      "read": 2.0,
      "share": 1.0,
      "search": 5.0,
      "cast": 0.0,
      "share_link": 0.0,
      "follow": 0.1
    },
    "agent_archetypes": {
      "enabled": true,
      "agent_downcast": true,
      "distribution": {
        "validator": 0.33,
        "broadcaster": 0.33,
        "explorer": 0.34
      }
    },
    "emotion_annotation": false
  },
  "agents": {
    "reading_from_follower_ratio": 0.6,
    "max_length_thread_reading": 5,
    "attention_window": 336,
    "probability_of_daily_follow": 0.1,
    "probability_of_secondary_follow": 0.1,
    "churn": {
      "enabled": true,
      "churn_probability": 0.1,
      "inactivity_threshold": 5,
      "churn_percentage": 0.05
    },
    "new_agents": {
      "enabled": true,
      "probability_new_agents": 0.1,
      "percentage_new_agents": 0.05
    }
  },
  "logging": {
    "enable_execution_log": true,
    "enable_actor_log": true,
    "enable_client_log": true,
    "enable_console_log": true
  }
}
```

#### Core Parameters

**Basic Settings:**
- `client_name` (string): Unique name for this client instance
- `namespace` (string): Ray namespace (must match server)
- `server.address` (string|null): Server address (null to use ray_config.temp)
- `server.port` (number|null): Server port

**Simulation Timing:**
- `simulation.num_days` (number): Days to simulate (0 = infinite)
- `simulation.num_slots_per_day` (number): Time slots per day (typically 24)
- `simulation.heartbeat_interval` (number, default: 5): Seconds between heartbeat signals

**Content Topics:**
- `simulation.discussion_topics` (array): Topics for content generation

**Activity Patterns:**
- `simulation.activity_profiles` (object): Named activity patterns (hour ranges)
- `simulation.hourly_activity` (object): Probability distribution across hours

#### LLM Configuration

**Text LLM (`llm`):**
```json
{
  "llm": {
    "address": "localhost",
    "port": 11434,
    "model": "llama3.2",
    "temperature": 0.7,
    "llm_api_key": "NULL",
    "llm_max_tokens": -1
  }
}
```
- Used for text generation (posts, comments, reactions)
- Connects to Ollama or compatible API

**Vision LLM (`llm_v`):**
```json
{
  "llm_v": {
    "address": "localhost",
    "port": 11434,
    "model": "minicpm-v",
    "temperature": 0.5,
    "llm_api_key": "NULL",
    "llm_max_tokens": 300
  }
}
```
- Used for image description and commentary
- Optional - if not configured, image actions are skipped
- Requires vision-capable model like minicpm-v

#### Action Likelihood Configuration

Controls relative probabilities of different agent actions:

```json
{
  "simulation": {
    "actions_likelihood": {
      "post": 3.0,
      "image": 0.0,
      "news": 0.0,
      "comment": 5.0,
      "read": 2.0,
      "share": 1.0,
      "search": 5.0,
      "cast": 0.0,
      "share_link": 0.0,
      "follow": 0.1
    }
  }
}
```

**Available Actions:**
- `post`: Create original text post
- `image`: Share image with commentary (requires llm_v)
- `news`: Share news from RSS feeds (page agents only)
- `comment`: Comment on posts
- `read`: Read and possibly react to posts
- `share`: Share/repost content
- `search`: Search for posts by topic interest
- `cast`: Reserved for future use
- `share_link`: Share external links
- `follow`: Follow another user

**Notes:**
- Values are relative probabilities (don't need to sum to 1.0)
- Set to 0 to disable an action type
- Image action requires llm_v configuration
- Search action primarily used by Explorer archetype

#### Agent Behavior Configuration

The `agents` section controls detailed behavior parameters:

```json
{
  "agents": {
    "reading_from_follower_ratio": 0.6,
    "max_length_thread_reading": 5,
    "attention_window": 336,
    "probability_of_daily_follow": 0.1,
    "probability_of_secondary_follow": 0.1
  }
}
```

**Parameters:**
- `reading_from_follower_ratio` (0.0-1.0): Proportion of posts from followed users in recommendations
- `max_length_thread_reading` (number): Maximum comment thread depth to read
- `attention_window` (number): Time slots of content visibility (default: 336 = 14 days × 24 slots)
- `probability_of_daily_follow` (0.0-1.0): Chance of evaluating new follows at end of each day
- `probability_of_secondary_follow` (0.0-1.0): Chance of follow/unfollow after content interactions

#### Follow Action Decay Configuration

Control time-based decay of follow action probability. This models the realistic behavior where users are most likely to follow others during their initial period of activity, with decreasing likelihood over time.

```json
{
  "agents": {
    "follow_action_decay": {
      "enabled": false,
      "decay_function": "exponential",
      "half_life_rounds": 168,
      "decay_rate": 0.01,
      "min_probability_ratio": 0.1
    }
  }
}
```

**Parameters:**
- `enabled` (boolean): Enable time-based follow action decay (default: false)
- `decay_function` (string): Type of decay function - "exponential" or "linear"
- `half_life_rounds` (number): For exponential decay, number of rounds until probability reaches 50% (e.g., 168 = 7 days with 24 slots/day)
- `decay_rate` (float): For linear decay, reduction rate per round (0.0-1.0)
- `min_probability_ratio` (float): Minimum decay multiplier (0.0-1.0), prevents probability from going to zero (default: 0.1 = 10% of original)

**Decay Functions:**

*Exponential Decay:* `multiplier = 0.5 ^ (rounds_since_join / half_life_rounds)`
- Suitable for modeling natural decline in follow behavior
- Example: With half_life_rounds=168 (7 days), after 7 days the follow probability is 50% of original, after 14 days it's 25%, etc.

*Linear Decay:* `multiplier = 1.0 - (decay_rate × rounds_since_join)`
- Provides constant reduction per round
- Example: With decay_rate=0.01, probability reduces by 1% per round
- Reaches min_probability_ratio when: rounds = (1.0 - min_probability_ratio) / decay_rate

**Notes:**
- Decay only applies to agents with a `joined_on` round recorded (new agents joining during simulation)
- Initial agents from `agent_population.json` (without `joined_on`) are not affected by decay
- Decay multiplier is applied to the `follow` action weight from `actions_likelihood`
- The final follow probability never goes below `min_probability_ratio` times the original weight

#### Logging Configuration

Control which log files are generated. See [LOGGING_CONFIG.md](../logging/LOGGING_CONFIG.md) for details.

```json
{
  "logging": {
    "enable_execution_log": true,
    "enable_actor_log": true,
    "enable_client_log": true,
    "enable_console_log": true
  }
}
```

---

## Advanced Features

### Agent Archetypes

Agent archetypes enable differentiated behaviors based on social media user types.

#### Configuration

```json
{
  "simulation": {
    "agent_archetypes": {
      "enabled": true,
      "agent_downcast": true,
      "distribution": {
        "validator": 0.33,
        "broadcaster": 0.33,
        "explorer": 0.34
      }
    }
  }
}
```

**Parameters:**
- `enabled` (boolean): Enable archetype-based behavior
- `agent_downcast` (boolean): Force validators/explorers to use rule-based behavior (cost optimization)
- `distribution` (object): Proportion of each archetype (should sum to ~1.0)

#### Archetype Behaviors

**1. Validator (Skeptical Content Consumers)**
- **Available actions**: share, read, share_link
- **Behavior**: Reactive users who evaluate and share but rarely create
- **Personality**: Skeptical, brief, authentic

**2. Broadcaster (Content Producers)**
- **Available actions**: post, image, share, comment
- **Behavior**: Active creators who post frequently and engage
- **Personality**: High energy, viral-seeking, controversial

**3. Broadcaster (Network Builders)**
- **Available actions**: search, follow
- **Behavior**: Focus on discovering content and building network
- **Personality**: Curious, asking questions

#### Agent Downcast Feature

The `agent_downcast` option reduces LLM costs while maintaining behavioral diversity:

- **Effect**: Validators and explorers use rule-based actions (faster, cheaper)
- **Unaffected**: Broadcasters maintain their LLM setting
- **Rationale**: Validators/explorers perform simpler actions (react, share, search), while broadcasters benefit from LLM-generated creative content
- **Cost Savings**: Significant reduction in LLM API calls

---

### Agent Population Dynamics

YSimulator models realistic population changes through churn and new agent features.

#### Agent Churn

Agents become inactive based on prolonged inactivity, simulating platform attrition.

**Configuration:**
```json
{
  "agents": {
    "churn": {
      "enabled": true,
      "churn_probability": 0.01,
      "inactivity_threshold": 5,
      "churn_percentage": 0.1
    }
  }
}
```

**Parameters:**
- `enabled` (boolean): Enable/disable churn evaluation
- `churn_probability` (0.0-1.0): Probability that inactive agent will churn
- `inactivity_threshold` (number): Days without activity before considered inactive
- `churn_percentage` (0.0-1.0): Percentage of inactive agents to evaluate each day

**How It Works:**
1. At end of each day, identify agents inactive for `inactivity_threshold` days
2. Randomly select `churn_percentage` of inactive agents as candidates
3. For each candidate, apply `churn_probability` to determine if they churn
4. Mark churned agents with `left_on` field set to current round ID
5. Exclude churned agents from future activity selection

**Database Fields:**
- `last_active_day`: Tracks last simulation day agent was active
- `left_on`: Round ID when agent churned (NULL = active, set = churned)

**Example Scenario:**
```
Day 1-5: Agent "user_123" is active
Day 6-10: Agent "user_123" is inactive
Day 11: Churn evaluation
  - Identified as inactive (5+ days)
  - Selected as candidate (within churn_percentage)
  - Probability check passes
  - Marked as churned (left_on = current_round_id)
Day 12+: Agent no longer selected for activities
```

#### New Agents

New agents can be dynamically added to model platform growth.

**Configuration:**
```json
{
  "agents": {
    "new_agents": {
      "enabled": true,
      "probability_new_agents": 0.01,
      "percentage_new_agents": 0.01
    }
  }
}
```

**Parameters:**
- `enabled` (boolean): Enable/disable new agent creation
- `probability_new_agents` (0.0-1.0): Probability each slot will be filled
- `percentage_new_agents` (0.0-1.0): Percentage of non-churned agents for slot calculation

**How It Works:**
1. At end of each day, count non-churned agents for this client
2. Calculate slots: `int(non_churned_agents * percentage_new_agents)`
3. For each slot, roll `probability_new_agents` to decide if new agent is created
4. Randomly select existing non-churned agent as template
5. Generate new agent with unique name but same attributes
6. Batch register all new agents with server
7. Add new agents to `agent_population.json` for persistence

**Name Generation:**
- Uses Faker library for realistic names
- Gender-aligned based on template agent's gender
- Spaces and periods replaced with underscores
- Uniqueness ensured by checking existing usernames

**Database Fields:**
- `joined_on`: Set to current Round ID when created
- `left_on`: Explicitly set to NULL (new agents not churned)
- `last_active_day`: Initialized when agent first becomes active
- All other fields copied from template

**Example Scenario:**
```
Population: 100 agents, 10 churned, 90 non-churned
Config: percentage_new_agents = 0.05, probability_new_agents = 0.5

Day 1 End:
  - Calculate slots: int(90 * 0.05) = 4 slots
  - Roll probability for each slot (50% each)
  - Expected: ~2 new agents (probabilistic)
  - Create as copies of random existing agents
  - Generate unique names: "John_Doe", "Jane_Smith"
  - Batch register with server
  - Update agent_population.json
Day 2+: New agents participate like original agents
```

#### Combined Churn and New Agents

Use both features together for realistic population dynamics:

```json
{
  "agents": {
    "churn": {
      "enabled": true,
      "churn_probability": 0.05,
      "inactivity_threshold": 7,
      "churn_percentage": 0.2
    },
    "new_agents": {
      "enabled": true,
      "probability_new_agents": 0.1,
      "percentage_new_agents": 0.05
    }
  }
}
```

**Population Dynamics:**
- **Attrition**: Inactive agents gradually churn
- **Growth**: New agents join to maintain/grow population
- **Balance**: Configure rates for desired trends
  - High churn + low new = declining population
  - Low churn + high new = growing population
  - Balanced rates = stable with turnover

**Performance Optimizations:**
- Both features use batch operations
- Before: ~116 server calls per day (80 churn + 36 new)
- After: 2 server calls per day (1 churn batch + 1 new batch)
- Performance gain: Up to 98% reduction

---

### Dynamic Social Network

YSimulator enables agents to form and break relationships during simulation.

#### Dynamic Follow Actions

Agents discover and follow other users using recommendation algorithms.

**Configuration:**

In `agent_population.json`, specify follow recommendation strategy per agent:

```json
{
  "id": 1,
  "username": "explorer_001",
  "archetype": "Explorer",
  "frecsys_type": "common_neighbors"
}
```

**Available Strategies:**
- `random`: Random user selection from non-following users
- `common_neighbors`: Friend-of-friend recommendations
- `jaccard`: Jaccard similarity of follow sets
- `adamic_adar`: Adamic/Adar index scoring
- `preferential_attachment`: Popular users (rich-get-richer)

**Implementation:**
- Server uses efficient query-based approaches
- SQL: JOIN queries, subqueries, aggregations
- Redis: Key-value operations
- Supports political leaning bias for homophily
- Follow action available to Explorer archetype by default

#### Daily Follow Evaluation

At end of each day, active agents can establish new follow relationships.

**Configuration:**
```json
{
  "agents": {
    "probability_of_daily_follow": 0.1
  }
}
```

**Behavior:**

At end of each day (last time slot), for each agent active during the day:
- With probability `daily_follow`, agent evaluates new follow candidates
- Uses agent's `frecsys_type` strategy to get top-10 suggestions
- Randomly selects one candidate from suggestions to follow
- Creates FOLLOW action in Follow table

**Use Cases:**
- Model gradual network growth over time
- Simulate daily social discovery behaviors
- Create realistic follow patterns independent of content
- Study long-term network evolution

#### Secondary Follow Behavior

After reading or commenting, agents can establish or break social ties with content authors.

**Configuration:**
```json
{
  "agents": {
    "probability_of_secondary_follow": 0.3
  }
}
```

**Behavior:**

With probability `secondary_follow`, after read or comment action:

- **Rule-based agents**: Randomly decide to follow, unfollow, or no change (equal probabilities)
- **LLM agents**: Heuristic decision based on current follow status
  - Not following: 30% chance to follow author
  - Already following: 10% chance to unfollow author
  - Otherwise: No change

**Implementation:**
- Tracks all read/comment interactions with post authors
- Evaluates after main action pipeline completes
- Checks current follow status before deciding
- Creates FOLLOW or UNFOLLOW actions with round timestamp

**Use Cases:**
- Model organic network growth through content interactions
- Simulate unfollowing based on content disagreement
- Create realistic social network evolution
- Study relationship formation patterns

---

### Opinion Dynamics

YSimulator supports configurable opinion dynamics models to simulate realistic opinion evolution and polarization.

**Configuration:**

```json
{
  "opinion_dynamics": {
    "enabled": true,
    "model_name": "bounded_confidence",
    "parameters": {
      "epsilon": 0.25,
      "mu": 0.5,
      "theta": 0.0,
      "cold_start": "neutral"
    },
    "opinion_groups": {
      "Strongly against": [0.0, 0.2],
      "Against": [0.2, 0.4],
      "Neutral": [0.4, 0.6],
      "In favor": [0.6, 0.8],
      "Strongly in favor": [0.8, 1.0]
    }
  }
}
```

#### Available Models

**1. Bounded Confidence** (`model_name: "bounded_confidence"`)
- Classic mathematical opinion dynamics model
- Agents update opinions when interacting with similar agents
- Applicable to all agent types (LLM and rule-based)

**Parameters:**
- `epsilon` (0.0-1.0): Confidence bound threshold - opinions within this distance influence each other
- `mu` (0.0-1.0): Convergence rate when within epsilon
- `theta` (0.0-1.0): Polarization rate when outside epsilon
- `cold_start` ("neutral" or "inherited"): Strategy for agents with no prior opinion

**2. LLM Evaluation** (`model_name: "llm_evaluation"`)
- LLM-based opinion assessment using natural language reasoning
- Evaluates agreement/disagreement with post content
- Only applicable to LLM agents (validated at runtime)

**Parameters:**
- `evaluation_scope` ("interlocutor_only" or "neighbors"): Scope of opinion evaluation
  - `"interlocutor_only"`: Only considers post author's opinion
  - `"neighbors"`: Also considers opinions of agents the reader follows
- `cold_start` ("neutral" or "inherited"): Strategy for agents with no prior opinion

#### Disabling Opinion Dynamics

To disable opinion dynamics:

```json
{
  "opinion_dynamics": {
    "enabled": false
  }
}
```

When disabled:
- No opinion updates occur during interactions
- Agents can still have initial opinions from `agent_population.json`
- The simulation runs normally without opinion evolution

You can also completely omit the `opinion_dynamics` section (equivalent to `enabled: false`).

#### Opinion Groups

Opinion groups map continuous values [0, 1] to discrete labels for:
- LLM prompt generation (readable opinion descriptions)
- Opinion shift calculations (LLM evaluation model)
- Logging and debugging

**Example Configuration:**
```json
{
  "opinion_groups": {
    "Strongly against": [0.0, 0.2],
    "Against": [0.2, 0.4],
    "Neutral": [0.4, 0.6],
    "In favor": [0.6, 0.8],
    "Strongly in favor": [0.8, 1.0]
  }
}
```

#### Examples

See the `example/` directory for complete configurations:
- `llm_population_100/`: Bounded confidence model (default)
- `llm_population_100_llm_opinion/`: LLM evaluation with neighbor influence
- `llm_population_100_no_opinion/`: Opinion dynamics disabled

**For detailed documentation**, see [OPINION_DYNAMICS.md](../features/OPINION_DYNAMICS.md).

---

## Agent Population Configuration

### File: `agent_population.json`

Defines agent profiles and automatic generation rules.

#### Structure

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
      "llm": true,
      "daily_activity_level": 3,
      "toxicity": "no",
      "leaning": "neutral",
      "language": "en",
      "recsys_type": "rchrono_followers",
      "frecsys_type": "common_neighbors"
    }
  ],
  "generation_config": {
    "num_additional_agents": 47,
    "cluster_distribution": {
      "weights": [0.4, 0.3, 0.3]
    },
    "llm_enabled_probability": 0.1,
    "age_range": [18, 65],
    "default_settings": {
      "education_level": "college",
      "toxicity": "no",
      "leaning": "neutral",
      "language": "en"
    }
  }
}
```

#### Agent Fields

**Identity:**
- `id` (number, required): Unique agent identifier
- `username` (string, required): Agent username
- `email` (string): Email address

**Demographics:**
- `age` (number): Age in years
- `education_level` (string): high_school, college, graduate, phd
- `gender` (string): male, female, non-binary
- `nationality` (string): Country code (US, UK, CA, AU, EU)
- `profession` (string): Job title or profession
- `language` (string): Language code (en, es, fr, de)

**Big Five Personality Traits:**
- `oe` (string): Openness to Experience (low/medium/high)
- `co` (string): Conscientiousness (low/medium/high)
- `ex` (string): Extraversion (low/medium/high)
- `ag` (string): Agreeableness (low/medium/high)
- `ne` (string): Neuroticism (low/medium/high)

**Behavior:**
- `activity_profile` (string): Activity pattern name
- `archetype` (string): Validator, Broadcaster, or Explorer
- `cluster` (number): Behavioral cluster (0=Validator, 1=Broadcaster, 2=Explorer)
- `llm` (boolean): Whether to use LLM for this agent
- `daily_activity_level` (number): Activity frequency (1-4)
- `toxicity` (string): yes/no
- `leaning` (string): Political leaning (neutral/left/right)

**Recommendation:**
- `recsys_type` (string): Content recommendation strategy
- `frecsys_type` (string): Follow recommendation strategy

#### Generation Config

Controls automatic agent generation:

```json
{
  "generation_config": {
    "num_additional_agents": 47,
    "cluster_distribution": {
      "weights": [0.4, 0.3, 0.3]
    },
    "llm_enabled_probability": 0.1,
    "age_range": [18, 65],
    "default_settings": {
      "education_level": "college",
      "toxicity": "no",
      "leaning": "neutral",
      "language": "en"
    }
  }
}
```

**Parameters:**
- `num_additional_agents`: Number of agents to generate automatically
- `cluster_distribution.weights`: Distribution for clusters [0, 1, 2]
- `llm_enabled_probability`: Probability generated agents use LLM
- `age_range`: Min and max age [min, max]
- `default_settings`: Default values for generated agents

**Process:**
1. Predefined agents in `agents` array created first
2. Additional agents generated using `generation_config`
3. All agents registered in `user_mgmt` database table at simulation start
4. Existing agents (by ID) not re-registered

---

## LLM Prompts Configuration

### File: `llm_prompts.json`

Defines personas and prompt templates for LLM interactions.

#### Structure

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
  "decide_search_action": {
    "system_template": "{persona} You searched for posts on a topic you're interested in and found relevant content.",
    "user_template": "You found this post:\n\n\"{post_content}\"\n\nHow do you want to engage? Reply with ONLY ONE WORD: COMMENT, SHARE, LIKE, LOVE, LAUGH, ANGRY, SAD, or IGNORE."
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

#### Prompt Templates

Each prompt has `system_template` and `user_template` with variable placeholders.

**Available Variables:**
- `{persona}`: Agent's persona from personas dictionary
- `{cluster_id}`: Agent's cluster ID (0, 1, or 2)
- `{day}`: Current simulation day
- `{slot}`: Current time slot
- `{post_content}`: Content of a post
- `{toxicity}`: Agent's toxicity level
- `{image_description}`: Description of an image
- `{topics_instruction}`: Topics to mention
- `{url}`: Image URL

#### Prompt Types

**1. generate_post**: Create original text posts
**2. decide_reaction**: Decide how to react to posts
**3. decide_search_action**: Engage with searched posts
**4. describe_image**: Generate image descriptions (vision LLM)
**5. generate_image_commentary**: Create posts about images

---

## Social Network Topology

### File: `network.csv` (Optional)

Defines initial social network structure through follow relationships.

#### Format

CSV with two columns (no header):
```csv
follower_username,user_username
```

Where:
- `follower_username`: Username of agent who follows
- `user_username`: Username of agent being followed

#### Example

```csv
validator_001,TechNewsPage
broadcaster_001,TechNewsPage
explorer_001,TechNewsPage
validator_001,broadcaster_001
broadcaster_001,explorer_001
explorer_001,validator_001
```

#### Behavior

1. **Automatic Loading**: If file exists, loaded when client connects
2. **Client-Specific**: Looks for `{client_name}_network.csv` first, falls back to `network.csv`
3. **Multi-Client Safe**: Checks for existing edges before loading
4. **Agent Validation**: Only creates edges for agents in `agent_population.json`
5. **Database Storage**: Stored in `follow` table with empty round (initial network)
6. **Recommendation Impact**: Influences content recommendations like `rchrono_followers`

#### Notes

- File is optional - agents start with no relationships if absent
- Usernames must exactly match (case-sensitive)
- No header row
- Empty lines ignored
- Dynamic follow relationships can still form during simulation

---

## Multi-Client Synchronization

The server handles multiple concurrent clients with different durations and potential failures.

### How It Works

1. **Barrier Synchronization**: Server waits for all **active** clients before advancing slot
2. **Graceful Completion**: Finished clients notify server and no longer block progression
3. **Heartbeat Mechanism**: Clients send periodic heartbeats (every 5 seconds)
4. **Timeout Detection**: Clients not sending heartbeats for `timeout_seconds` automatically removed

### Client States

- **Active**: Registered and participating
- **Completed**: Finished activities, no longer blocks others
- **Stale**: Haven't sent heartbeat within timeout, automatically removed

### Heartbeat-Based Liveness

- **Processing time doesn't matter**: Long-running slots OK as long as heartbeats arrive
- **Heartbeat interval**: Clients send every `heartbeat_interval` seconds (default: 5s)
- **Timeout detection**: Only clients **stopping heartbeats** for > `timeout_seconds` marked stale
- **Recommendation**: Set `timeout_seconds` to 10-12x `heartbeat_interval`

**Example**: If `heartbeat_interval = 5` and `timeout_seconds = 60`, a client processing for 10 minutes is fine as long as heartbeats arrive every 5 seconds.

### Client-Side Simulation Steps

**Design**: Client handles its own progression, server provides coordination.

**Registration Flow:**
1. Client registers with server, specifying `num_days` (informational)
2. Server responds with current `start_day` and `start_slot`
3. Client tracks progress locally from starting point
4. Client exits when `current_day >= start_day + num_days`

**On Restart:**
- Client re-registers and receives current server time as new starting point
- Runs for full configured duration from new starting point

**Example:**
```
Server at day 10
Client joins with num_days = 3
Server returns: start_day = 10, start_slot = 5
Client runs while current_day < 13 (days 10, 11, 12)
If client restarts at day 20:
  - Server returns: start_day = 20
  - Client runs days 20-23 (full 3 days from new start)
```

### Example Scenario

```
Initial: 3 clients (A, B, C) start at Day 1
Day 1-4: All submit, server advances
Day 5: Client A finishes (started day 1, num_days=5)
  → A exits and calls complete_client()
  → Server marks A as completed
  → Only B and C block advancement
Day 6-7: B and C continue without A
Day 7: Client B finishes
Day 8: New Client D joins (server at day 8, configured for 3 days)
  → D receives start_day=8
  → D runs until day 11
Day 10: Client C finishes
Day 11: Client D finishes → Simulation complete
```

### Configuration

**Server (`server_config.json`):**
```json
{
  "timeout_seconds": 60
}
```

**Client (`simulation_config.json`):**
```json
{
  "simulation": {
    "heartbeat_interval": 5
  }
}
```

**Recommendations:**
- `heartbeat_interval`: 3-10 seconds
- `timeout_seconds`: 10-12x heartbeat_interval minimum
- High-latency networks: Increase both proportionally
- Development/debugging: 300-600s timeout to avoid interruptions

---

## Logging Configuration

Both server and client generate rotating JSON logs. Log file generation is configurable.

### Log Files

**Server:**
- `logs/{server_name}_server.log` - Main server process
- `logs/{server_name}_actor.log` - Orchestrator actor
- `logs/_server.log` - Request tracking

**Client:**
- `logs/{client_name}_execution.log` - Main client process
- `logs/{client_id}_actor.log` - Simulation actor
- `logs/{client_id}_client.log` - Agent actions

### Log Configuration

Control which logs are generated in `server_config.json` and `simulation_config.json`:

**Server:**
```json
{
  "logging": {
    "enable_server_log": true,
    "enable_actor_log": true,
    "enable_request_log": true,
    "enable_console_log": true
  }
}
```

**Client:**
```json
{
  "logging": {
    "enable_execution_log": true,
    "enable_actor_log": true,
    "enable_client_log": true,
    "enable_console_log": true
  }
}
```

All options default to `true`. Set to `false` to disable specific logs.

### Log Format

JSON format with structure:
```json
{
  "timestamp": "2025-12-31T20:00:00.000Z",
  "level": "INFO",
  "message": "Agent registration complete",
  "module": "server",
  "function": "register_agents",
  "line": 150,
  "registered": 50,
  "execution_time_ms": 125.5
}
```

### Log Rotation

- **Maximum size**: 10MB per file
- **Backups**: 5 files kept
- **Compression**: Rotated files gzip-compressed with `.gz` extension
- **Format**: JSON, one entry per line

**For detailed logging documentation**, see:
- [LOGGING_CONFIG.md](../logging/LOGGING_CONFIG.md) - Complete logging configuration guide
- [SERVER_LOGGING.md](../logging/SERVER_LOGGING.md) - Server request log format and analysis
- [ACTION_LOGGING.md](../logging/ACTION_LOGGING.md) - Client action log format and summaries

---

## Configuration Examples

### Example 1: Development Setup (SQLite, Full Logging)

**server_config.json:**
```json
{
  "server_name": "dev_server",
  "database": {
    "type": "sqlite",
    "sqlite": {"filename": "dev.db"}
  },
  "min_to_start": 1,
  "logging": {
    "enable_server_log": true,
    "enable_actor_log": true,
    "enable_request_log": true
  }
}
```

**simulation_config.json:**
```json
{
  "client_name": "dev_client",
  "simulation": {
    "num_days": 2,
    "num_slots_per_day": 24
  },
  "logging": {
    "enable_execution_log": true,
    "enable_actor_log": true,
    "enable_client_log": true
  }
}
```

### Example 2: Production Setup (PostgreSQL, Minimal Logging)

**server_config.json:**
```json
{
  "server_name": "prod_server",
  "database": {
    "type": "postgresql",
    "postgresql": {
      "host": "db.example.com",
      "port": 5432,
      "database": "ysimulator_prod",
      "username": "ysim_user",
      "password": "secure_password"
    }
  },
  "min_to_start": 5,
  "timeout_seconds": 120,
  "logging": {
    "enable_server_log": true,
    "enable_actor_log": false,
    "enable_request_log": false
  }
}
```

### Example 3: Large-Scale Simulation (Redis, Churn, New Agents)

**server_config.json:**
```json
{
  "database": {"type": "postgresql", ...},
  "redis": {
    "enabled": true,
    "host": "redis.example.com",
    "sliding_window_days": 2
  }
}
```

**simulation_config.json:**
```json
{
  "simulation": {
    "num_days": 30,
    "agent_archetypes": {
      "enabled": true,
      "agent_downcast": true
    }
  },
  "agents": {
    "churn": {
      "enabled": true,
      "churn_probability": 0.05,
      "inactivity_threshold": 7,
      "churn_percentage": 0.1
    },
    "new_agents": {
      "enabled": true,
      "probability_new_agents": 0.1,
      "percentage_new_agents": 0.05
    }
  }
}
```

### Example 4: Multi-Client Distributed Simulation

**Server** (run once):
```bash
python run_server.py --config shared_config
```

**Client 1** (10 days, 1000 agents):
```bash
python run_client.py --config shared_config
# simulation_config.json: client_name="client_1", num_days=10
```

**Client 2** (5 days, 500 agents):
```bash
python run_client.py --config shared_config
# simulation_config.json: client_name="client_2", num_days=5
# Uses client_2_agent_population.json
```

---

## Related Documentation

- **[LOGGING_CONFIG.md](../logging/LOGGING_CONFIG.md)** - Comprehensive logging configuration guide
- **[SERVER_LOGGING.md](../logging/SERVER_LOGGING.md)** - Server request log format and analysis  
- **[ACTION_LOGGING.md](../logging/ACTION_LOGGING.md)** - Client action log format and summaries
- **[ARCHITECTURE.md](../architecture/ARCHITECTURE.md)** - System architecture overview
- **[EXTENDING.md](../development/EXTENDING.md)** - Guide to extending YSimulator

---

## Quick Reference

### Required Configuration Files

| Role | Files Required |
|------|----------------|
| Server | `server_config.json` |
| Client | `simulation_config.json`, `agent_population.json`, `llm_prompts.json` |

### Optional Configuration Files

| File | Purpose |
|------|---------|
| `network.csv` | Initial social network topology |
| `{client_name}_agent_population.json` | Client-specific agent profiles |
| `{client_name}_llm_prompts.json` | Client-specific LLM prompts |
| `{client_name}_network.csv` | Client-specific network |

### Default Values

| Parameter | Default | Range |
|-----------|---------|-------|
| `num_days` | 0 (infinite) | 0+ |
| `num_slots_per_day` | 24 | 1+ |
| `heartbeat_interval` | 5 seconds | 1-60 |
| `timeout_seconds` | 60 seconds | 10-600 |
| `min_to_start` | 1 client | 1+ |
| `attention_window` | 336 slots | 1+ |
| All logging options | true | true/false |

### Command Line Reference

```bash
# Run server
python run_server.py --config path/to/config

# Run client
python run_client.py --config path/to/config

# Use current directory (default)
python run_server.py
python run_client.py
```
