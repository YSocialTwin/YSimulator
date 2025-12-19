# YSimulator Architecture

This document provides a comprehensive overview of the YSimulator system architecture, component organization, and interaction patterns.

## Table of Contents
- [System Overview](#system-overview)
- [High-Level Architecture](#high-level-architecture)
- [Component Details](#component-details)
- [Data Flow](#data-flow)
- [Coordination Mechanisms](#coordination-mechanisms)
- [Technology Stack](#technology-stack)

## System Overview

YSimulator is a **distributed social media simulation framework** designed to model agent behavior across multiple concurrent clients coordinated by a central server. The system uses **Ray** for distributed computing, **SQLAlchemy** for database abstraction, and supports multiple storage backends (SQLite, PostgreSQL, MySQL, Redis).

### Key Characteristics
- **Distributed**: Multiple clients run simultaneously, each managing a subset of agents
- **Coordinated**: Central server ensures temporal synchronization across all clients
- **Scalable**: Ray actors enable horizontal scaling
- **Flexible**: Pluggable storage backends and configurable parameters
- **Observable**: Comprehensive JSON logging with performance metrics

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         YSimulator System                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐         ┌──────────────┐                      │
│  │   Client 1   │         │   Client 2   │    ... Client N      │
│  │              │         │              │                       │
│  │ ┌──────────┐ │         │ ┌──────────┐ │                      │
│  │ │  Agent   │ │         │ │  Agent   │ │                      │
│  │ │ Population│ │         │ │ Population│ │                      │
│  │ └──────────┘ │         │ └──────────┘ │                      │
│  │              │         │              │                       │
│  │ ┌──────────┐ │         │ ┌──────────┐ │                      │
│  │ │   LLM    │ │         │ │   LLM    │ │                      │
│  │ │ Service  │ │         │ │ Service  │ │                      │
│  │ └──────────┘ │         │ └──────────┘ │                      │
│  └──────┬───────┘         └──────┬───────┘                      │
│         │                        │                               │
│         │    Ray Remote Calls    │                               │
│         └────────────┬───────────┘                               │
│                      │                                            │
│              ┌───────▼────────┐                                  │
│              │                │                                   │
│              │  Orchestrator  │                                   │
│              │     Server     │                                   │
│              │                │                                   │
│              │  ┌──────────┐  │                                   │
│              │  │  Barrier │  │                                   │
│              │  │  Sync    │  │                                   │
│              │  └──────────┘  │                                   │
│              │                │                                   │
│              │  ┌──────────┐  │                                   │
│              │  │ Database │  │                                   │
│              │  │Middleware│  │                                   │
│              │  └──────────┘  │                                   │
│              └───────┬────────┘                                  │
│                      │                                            │
│                      │                                            │
│         ┌────────────┼────────────┐                              │
│         │            │            │                               │
│    ┌────▼────┐  ┌───▼────┐  ┌───▼────┐                          │
│    │  Redis  │  │ SQLite │  │  Postgre│   MySQL                  │
│    │  Cache  │  │        │  │   SQL   │                          │
│    └─────────┘  └────────┘  └────────┘                          │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Client Components

#### SimulationClient (Ray Actor)
**Location**: `YClient/client.py`

**Responsibilities**:
- Manage agent population lifecycle
- Execute simulation steps (day/slot iteration)
- Coordinate agent actions
- Maintain heartbeat with server
- Track local simulation progress

**Key Methods**:
```python
run()                          # Main simulation loop
_execute_slot()                # Execute one time slot
_perform_agent_actions()       # Trigger agent behaviors
_send_heartbeat()              # Keep-alive signal to server
complete_client()              # Notify server of completion
```

**State**:
- `agents`: List of agent instances
- `start_day`, `start_slot`: Entry point from server
- `max_day`: Local calculation of when to stop
- `llm_service`: Connection to LLM for content generation

#### LLM Service
**Location**: `LLM_interactions/llm_service.py`

**Responsibilities**:
- Generate agent content (posts, comments, replies)
- Manage prompt templates per agent cluster
- Handle LLM API communication
- Apply temperature and model configuration

**Key Methods**:
```python
generate_post()                # Create social media post
generate_comment()             # Create comment on post
apply_persona()                # Tailor content to agent personality
```

**Configuration**:
- LLM address and port
- Model selection
- Temperature settings
- Prompt templates per cluster

#### Agent Profiles
**Location**: `classes/models.py` (AgentProfile dataclass)

**Properties**:
- **Identity**: id, username, email
- **Personality**: Big Five traits (OE, CO, EX, AG, NE)
- **Demographics**: age, gender, nationality, education, profession
- **Behavior**: daily_activity_level, activity_profile, toxicity
- **Social**: leaning, archetype, cluster
- **Technical**: llm (boolean), owner

### 2. Server Components

#### OrchestratorServer (Ray Actor)
**Location**: `YServer/server.py`

**Responsibilities**:
- Coordinate temporal progression (day/slot)
- Manage client registration and lifecycle
- Enforce barrier synchronization
- Track heartbeats and detect stale clients
- Distribute actions to storage
- Trigger daily consolidation (if Redis enabled)

**Key Methods**:
```python
register_client()              # Register new client
get_instruction()              # Provide time coordination
submit_action()                # Store client actions (posts, interactions)
complete_client()              # Mark client as finished
heartbeat()                    # Update client liveness
advance_time()                 # Move to next time slot
```

**State**:
- `current_day`, `current_slot`: Simulation time
- `registered_clients`: Set of all clients
- `completed_clients`: Set of finished clients
- `last_heartbeat`: Dict mapping client_id to timestamp
- `barrier`: Counter for synchronization

#### DatabaseMiddleware
**Location**: `classes/db_middleware.py`

**Responsibilities**:
- Abstract storage backend (SQL vs Redis)
- Provide unified API for data operations
- Manage Redis sliding window consolidation
- Handle SQLAlchemy session management
- Build appropriate connection strings

**Key Methods**:
```python
register_user()                # Store agent profile in User_mgmt table
add_post()                     # Store social media post
add_interaction()              # Store interaction (like, comment, etc.)
get_user()                     # Retrieve user profile
get_recent_posts()             # Query recent posts
consolidate_day()              # Move Redis data to SQL (daily)
```

**Storage Strategy**:
- **Redis**: High-speed cache for recent data (if enabled)
- **SQL**: Persistent storage for all data
- **Sliding Window**: Automatic pruning of old Redis data
- **Dual Write**: Write to both Redis and SQL for durability

### 3. Data Models

#### Database Models
**Location**: `classes/models.py`

**User_mgmt**: Agent profiles
- Primary storage for agent identity and characteristics
- Used by both server and analysis tools
- Fields map to AgentProfile dataclass

**PostModel**: Social media posts
- UUID-based ID for distributed generation
- Links to user via user_id foreign key
- Includes temporal context (day, slot)
- Stores content, likes, shares

**InteractionModel**: User interactions
- UUID-based ID
- Captures interaction type (like, comment, share, etc.)
- Links to both user and target post
- Includes temporal and spatial context

#### Ray Communication Models
**Location**: `classes/ray_models.py`

**SimulationInstruction**:
```python
@dataclass
class SimulationInstruction:
    status: str          # "WAIT" or "PROCEED"
    day: int             # Current simulation day
    slot: int            # Current time slot
```

**AgentProfile**: Lightweight dataclass for Ray message passing

### 4. Configuration System

#### Directory-Based Configuration
**Location**: Configuration directory (default: current dir)

**Files**:
```
config_dir/
├── server_config.json         # Server parameters
├── simulation_config.json     # Client parameters
├── agent_population.json      # Agent definitions
├── llm_prompts.json          # Prompt templates
├── simulation.db             # Database (auto-created)
├── ray_config.temp           # Ray temp file (auto-created)
└── logs/                     # JSON logs (auto-created)
    ├── {server_name}_server.log
    ├── {server_name}_actor.log
    ├── {client_name}_client.log
    └── {client_name}_actor.log
```

**Common Utils**:
**Location**: `common_utils.py`

Provides `validate_config_directory()` for consistent validation across client and server.

## Data Flow

### 1. Initialization Flow

```
┌────────────┐
│ run_server │
└─────┬──────┘
      │
      ├─ Load server_config.json
      ├─ Initialize database (SQLAlchemy + optional Redis)
      ├─ Create Ray actor: OrchestratorServer
      └─ Wait for min_to_start clients
           │
           │  ┌────────────┐
           └──┤ run_client │
              └─────┬──────┘
                    │
                    ├─ Load simulation_config.json
                    ├─ Load agent_population.json
                    ├─ Load llm_prompts.json
                    ├─ Create Ray actor: SimulationClient
                    ├─ Register with server
                    │   └─→ Server returns start_day, start_slot
                    ├─ Register agents in User_mgmt table
                    └─ Begin simulation loop
```

### 2. Simulation Loop Flow

```
For each client (parallel):
    │
    ├─ Calculate: current_day >= max_day? → Exit
    │
    ├─ Get instruction from server
    │   └─→ Server: Check barrier
    │       ├─ All clients submitted? → PROCEED (advance time)
    │       └─ Waiting for others? → WAIT
    │
    ├─ If WAIT: sleep and retry
    │
    ├─ If PROCEED:
    │   ├─ Execute slot actions
    │   │   ├─ For each agent:
    │   │   │   ├─ Decide action (post, interact, idle)
    │   │   │   ├─ Generate content (via LLM)
    │   │   │   └─ Submit action to server
    │   │   │       └─→ Server stores via DatabaseMiddleware
    │   │   └─ Complete
    │   │
    │   ├─ Submit completion to server (barrier counter++)
    │   └─ Send heartbeat
    │
    └─ Loop to next iteration
```

### 3. Action Submission Flow

```
Agent decides to post
    │
    ├─ LLMService generates content
    │   └─ Uses prompt template for agent's cluster
    │
    └─ Client calls server.submit_action()
        │
        └─→ Server (OrchestratorServer)
            │
            ├─ Add temporal context (day, slot)
            ├─ Generate UUID for post
            │
            └─ DatabaseMiddleware.add_post()
                │
                ├─ If Redis enabled:
                │   ├─ Store in Redis (fast cache)
                │   └─ Index by day for consolidation
                │
                └─ Store in SQL (persistent)
```

### 4. Time Progression Flow

```
Server barrier check:
    │
    ├─ Check for stale clients (missing heartbeats)
    │   └─ Remove stale → Update active_clients set
    │
    ├─ Count submissions this slot
    │   └─ submitted_active_clients == active_clients?
    │
    └─ If all submitted:
        │
        ├─ Increment current_slot
        │
        ├─ If slot >= slots_per_day:
        │   ├─ Increment current_day
        │   ├─ Reset current_slot = 0
        │   │
        │   └─ If Redis enabled:
        │       └─ consolidate_day()
        │           ├─ Save all Redis data to SQL
        │           ├─ Remove data older than sliding_window_days
        │           └─ Log metrics
        │
        ├─ Reset barrier counter
        │
        └─ Return PROCEED to waiting clients
```

### 5. Heartbeat and Liveness Flow

```
Client (every heartbeat_interval seconds):
    │
    └─ server.heartbeat(client_id)
        └─→ Server updates last_heartbeat[client_id] = now()

Server (before each barrier check):
    │
    └─ _check_for_stale_clients()
        │
        ├─ For each registered client:
        │   ├─ time_since_heartbeat = now() - last_heartbeat[client_id]
        │   └─ If time_since_heartbeat > timeout_seconds:
        │       ├─ Log warning
        │       ├─ Remove from registered_clients
        │       └─ Remove from last_heartbeat dict
        │
        └─ Update active_clients = registered - completed
```

### 6. Client Completion Flow

```
Client reaches max_day:
    │
    ├─ server.complete_client(client_id)
    │   └─→ Server:
    │       ├─ Add to completed_clients set
    │       ├─ Update active_clients = registered - completed
    │       └─ Log completion
    │
    ├─ Log final statistics
    │
    └─ Exit simulation loop
```

## Coordination Mechanisms

### 1. Barrier Synchronization

**Purpose**: Ensure all clients progress through time together

**Implementation**:
```python
# Server maintains
barrier_counter = 0          # Submissions this slot
active_clients = registered - completed

# Each client submits when done with slot
barrier_counter += 1

# Server checks before returning instruction
if barrier_counter >= len(active_clients):
    advance_time()
    barrier_counter = 0
    return PROCEED
else:
    return WAIT
```

**Benefits**:
- Prevents time desynchronization
- Enables causal consistency (actions happen in order)
- Allows coordination of global events

### 2. Heartbeat Mechanism

**Purpose**: Detect crashed/disconnected clients without blocking healthy ones

**Implementation**:
```python
# Client sends periodically
every heartbeat_interval seconds:
    server.heartbeat(client_id)

# Server checks before barrier
for client_id in registered_clients:
    if now() - last_heartbeat[client_id] > timeout_seconds:
        remove_client(client_id)
```

**Benefits**:
- Decouples processing time from liveness
- Prevents false positives on busy clients
- Automatic recovery from client failures

### 3. Client-Side Step Management

**Purpose**: Simplify server logic by delegating day counting to clients

**Implementation**:
```python
# Server provides starting point
response = server.register_client(num_days=3)
start_day = response["start_day"]      # e.g., 10

# Client tracks locally
max_day = start_day + num_days         # 13
current_day = start_day                # From instructions

# Client checks each iteration
if current_day >= max_day:
    exit()
```

**Benefits**:
- Simpler server (no per-client state tracking)
- Client autonomy (manages own timeline)
- Clear separation of concerns

## Technology Stack

### Core Technologies
- **Ray**: Distributed computing framework
- **SQLAlchemy**: Database ORM and abstraction
- **Python 3.8+**: Implementation language
- **JSON**: Configuration and logging format

### Storage Backends
- **SQLite**: Default file-based database
- **PostgreSQL**: Production-grade RDBMS
- **MySQL**: Production-grade RDBMS
- **Redis**: Optional high-performance cache

### External Services
- **LLM API**: Content generation (configurable endpoint)

### Development Tools
- **Black**: Code formatting
- **isort**: Import sorting
- **Pre-commit**: Automatic formatting on commit

## Component Responsibilities Summary

### What the Server Does
- ✅ Coordinate temporal progression (day/slot)
- ✅ Manage client registration and lifecycle
- ✅ Enforce barrier synchronization
- ✅ Track heartbeats and detect failures
- ✅ Store actions via DatabaseMiddleware
- ✅ Trigger daily Redis consolidation
- ✅ Provide starting point to clients

### What the Server Does NOT Do
- ❌ Track per-client simulation progress
- ❌ Decide when clients should stop
- ❌ Manage agent behavior
- ❌ Generate content

### What the Client Does
- ✅ Manage agent population
- ✅ Execute simulation steps locally
- ✅ Track own progress (day counting)
- ✅ Decide when to exit (based on max_day)
- ✅ Send heartbeats regularly
- ✅ Submit actions to server
- ✅ Generate content via LLM

### What the Client Does NOT Do
- ❌ Coordinate with other clients directly
- ❌ Manage simulation time (receives from server)
- ❌ Store data (delegates to server)
- ❌ Track other clients' state

### What the DatabaseMiddleware Does
- ✅ Abstract storage backend selection
- ✅ Provide unified API for operations
- ✅ Build appropriate connection strings
- ✅ Manage SQLAlchemy sessions
- ✅ Handle Redis sliding window
- ✅ Consolidate Redis to SQL daily

### What the DatabaseMiddleware Does NOT Do
- ❌ Implement business logic
- ❌ Coordinate clients
- ❌ Manage simulation time

## Conclusion

YSimulator's architecture follows a **coordinator-worker pattern** where:
- **Server** coordinates temporal progression and manages barriers
- **Clients** independently execute simulations and manage local state
- **DatabaseMiddleware** abstracts storage for flexibility and performance
- **Ray** enables distributed execution without manual networking code

This design provides:
- **Scalability**: Add clients without server changes
- **Fault Tolerance**: Automatic stale client detection and removal
- **Flexibility**: Pluggable storage backends
- **Observability**: Comprehensive logging at all layers
- **Simplicity**: Clear separation of concerns

For implementation details, see:
- [Configuration Guide](CONFIG.md)
- [Extension Guide](EXTENDING.md)
- [Code Formatting](FORMATTING.md)
