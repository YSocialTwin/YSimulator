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
- Generate image descriptions using vision LLM (llm_v)
- Generate image commentary for sharing actions
- Manage prompt templates per agent cluster
- Handle LLM API communication (text and vision models)
- Apply temperature and model configuration

**Key Methods**:
```python
generate_post()                # Create social media post
generate_comment()             # Create comment on post
describe_image()               # Vision LLM image description
generate_image_commentary()    # Generate post about an image
apply_persona()                # Tailor content to agent personality
```

**Configuration**:
- LLM address and port (text model)
- LLM_v address and port (vision model, optional)
- Model selection (text and vision)
- Temperature settings
- Prompt templates per cluster

**Features**:
- **Dual LLM Support**: Separate text and vision model configurations
- **Image Processing**: Extracts and describes images from RSS feeds using vision models
- **Async Operations**: Non-blocking LLM calls for performance

#### Agent Profiles
**Location**: `classes/models.py` (AgentProfile dataclass)

**Properties**:
- **Identity**: id, username, email
- **Personality**: Big Five traits (OE, CO, EX, AG, NE)
- **Demographics**: age, gender, nationality, education, profession
- **Behavior**: daily_activity_level, activity_profile, toxicity
- **Social**: leaning, archetype, cluster
- **Technical**: llm (boolean), owner
- **Archetype Override**: agent_downcast configuration can force validators and explorers to use rule-based behavior

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
- Delegate interest management to InterestManager

**Key Methods**:
```python
register_client()              # Register new client
get_instruction()              # Provide time coordination
submit_action()                # Store client actions (posts, interactions)
complete_client()              # Mark client as finished
heartbeat()                    # Update client liveness
advance_time()                 # Move to next time slot
get_updated_agent_interests()  # Get current interests for persistence
```

**State**:
- `current_day`, `current_slot`: Simulation time
- `registered_clients`: Set of all clients
- `completed_clients`: Set of finished clients
- `last_heartbeat`: Dict mapping client_id to timestamp
- `barrier`: Counter for synchronization
- `interest_manager`: InterestManager instance for topic/interest operations

#### InterestManager
**Location**: `YServer/interests_modeling/interest_manager.py`

**Responsibilities**:
- Validate and extract agent interest data
- Maintain in-memory agent interest state
- Implement sliding window attention mechanism
- Handle article topic extraction and storage
- Map topic IDs to names
- Recompute interests with forgetting mechanism

**Key Methods**:
```python
validate_and_extract_interests()           # Validate interest format
initialize_agent_interests()               # Setup during registration
recompute_agent_interests_from_window()    # Single agent recomputation
recompute_all_agent_interests()            # Batch recomputation (daily)
get_agent_interests()                      # Get current state
store_article_topics()                     # Persist article topics
get_article_topics()                       # Retrieve article topics
```

**Features**:
- **Sliding Window**: Queries user_interest entries within attention_window
- **Forgetting Mechanism**: Topics with count 0 automatically removed
- **Topic Mapping**: Efficient UUID-to-name lookups
- **Article Topics**: LLM-extracted topics from news articles

#### DatabaseMiddleware
**Location**: `classes/db_middleware.py`

**Responsibilities**:
- Abstract storage backend (SQL vs Redis)
- Provide unified API for data operations
- Manage Redis sliding window consolidation
- Handle SQLAlchemy session management
- Build appropriate connection strings
- Support interest/topic database operations

**Key Methods**:
```python
register_user()                            # Store agent profile in User_mgmt table
add_post()                                 # Store social media post
add_interaction()                          # Store interaction (like, comment, etc.)
get_user()                                 # Retrieve user profile
get_recent_posts()                         # Query recent posts
consolidate_day()                          # Move Redis data to SQL (daily)
add_or_get_interest()                      # Store/retrieve topic
add_user_interest()                        # Record user-topic interaction
add_post_topic()                           # Link post to topic
get_post_topics()                          # Get topics for a post
get_user_interests_in_window()             # Query interests in temporal window
compute_interest_counts_in_window()        # Count interests in window
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
- reaction_count: Automatically incremented on reactions/comments
- image_id: Optional reference to Image table

**InteractionModel**: User interactions
- UUID-based ID
- Captures interaction type (like, comment, share, etc.)
- Links to both user and target post
- Includes temporal and spatial context
- Automatically increments parent post reaction_count

**Follow**: Social network relationships
- Tracks follow/unfollow actions between users
- follower_id: User who is following
- user_id: User being followed
- action: "follow" or "unfollow"
- round: Temporal context (simulation round)
- Supports dynamic network evolution
- Used by follow recommendation algorithms

**Article**: News articles from RSS feeds
- id (UUID): Article identifier
- title, url: Article metadata
- website_id: Reference to source website
- published: Publication timestamp
- Extracted by page agents

**Image**: Images from RSS feeds
- id (UUID): Image identifier
- url: Image URL from RSS feed
- description: Vision LLM-generated description
- article_id: Reference to source article
- Used for image sharing action

**Interest**: Topic definitions
- iid (UUID): Unique interest identifier
- interest (Text): Topic name
- Deduplicated storage of all topics
- Referenced by user_interest, post_topics, article_topics

**UserInterest**: User-topic interactions
- id (UUID): Record identifier
- user_id (UUID): Agent who has this interest
- interest_id (UUID): Reference to Interest table
- round_id (UUID): When this interest was recorded
- Supports temporal analysis and sliding window forgetting

**PostTopic**: Post-topic associations
- id (UUID): Record identifier
- post_id (UUID): The post
- topic_id (UUID): Reference to Interest table
- Links posts to their topics for analysis

**ArticleTopic**: Article-topic associations
- id (UUID): Record identifier
- article_id (UUID): The news article
- topic_id (UUID): Reference to Interest table
- Stores LLM-extracted topics from articles

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
    │   │   │   ├─ Decide action type (post, read, comment, share, follow, etc.)
    │   │   │   ├─ For FOLLOW action:
    │   │   │   │   ├─ Request follow suggestions from server (based on agent's frecsys_type)
    │   │   │   │   ├─ Server computes using recommendation algorithm
    │   │   │   │   ├─ Select one candidate (LLM decision or random)
    │   │   │   │   └─ Create FOLLOW action
    │   │   │   ├─ For READ/COMMENT action:
    │   │   │   │   ├─ Get recommended posts (based on recsys_type)
    │   │   │   │   ├─ Select post and generate reaction/comment
    │   │   │   │   └─ Secondary follow evaluation (with probability):
    │   │   │   │       ├─ Check if following post author
    │   │   │   │       ├─ Decide follow/unfollow/no_change
    │   │   │   │       └─ Create FOLLOW/UNFOLLOW action if needed
    │   │   │   ├─ Generate content (via LLM for LLM agents)
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

## Recommendation Systems

### 1. Content Recommendation System

Agents discover posts to read and react to using configurable recommendation strategies.

**Architecture**:
```
Agent → ContentRecSys → Server.get_recommended_posts() → Database Query → Post IDs
```

**Strategies**:
- `random`: Random post ordering
- `rchrono`: Reverse chronological (newest first)
- `rchrono_popularity`: Chronological with popularity boost
- `rchrono_followers`: Prioritizes posts from followed users
- `rchrono_followers_popularity`: Combines followers and popularity
- `rchrono_comments`: Prioritizes highly commented posts
- `common_interests`: Posts with common topic interests
- `common_user_interests`: Posts by users with common interests
- `similar_users_react`: Posts from similar users (by reactions)
- `similar_users_posts`: Posts from similar users (by posting)

**Configuration**: Per-agent via `recsys_type` field

### 2. Follow Recommendation System

Agents discover users to follow using link prediction and network analysis algorithms.

**Architecture**:
```
Agent → FollowRecSysRay → Server.get_follow_suggestions() → Query-Based Algorithm → User IDs
```

**Strategies**:

1. **Random**: Random selection from non-following users
   - SQL: Direct query with filtering
   - Redis: SMEMBERS with filtering

2. **Common Neighbors**: Friend-of-friend recommendations
   - SQL: JOIN query to find users agent's friends follow
   - Redis: Iterate through friend's follows
   - Score: Count of mutual connections

3. **Jaccard Similarity**: Similarity of follow sets
   - SQL: Intersection/union via subqueries
   - Redis: Set operations on follows
   - Score: |intersection| / |union|

4. **Adamic/Adar Index**: Weighted common neighbors
   - SQL: Two-step approach:
     1. Find common neighbors via JOIN
     2. Batch query degrees for scoring
   - Redis: Same two-step logic with key lookups
   - Score: Σ(1/log(degree)) for each common neighbor
   - Prefers connections through less-connected intermediaries

5. **Preferential Attachment**: Popularity-based
   - SQL: COUNT query for follower popularity
   - Redis: Iterate and count followers
   - Score: Number of followers (rich-get-richer)

**Implementation Details**:
- No NetworkX dependency (eliminated for scalability)
- Query-based approaches for both SQL and Redis
- Efficient batch operations
- Graceful fallback to random if queries fail
- Supports political leaning bias (homophily parameter)

**Configuration**: Per-agent via `frecsys_type` field

### 3. Secondary Follow Mechanism

After content interactions (read/comment), agents evaluate relationship changes.

**Architecture**:
```
Agent reads/comments → Track interaction → Evaluate with probability → Check status → FOLLOW/UNFOLLOW
```

**Process**:
1. Track all read/comment interactions with post authors
2. With probability `secondary_follow`, evaluate each interaction:
   - Check if currently following author
   - Rule-based: Random decision (follow/unfollow/no_change)
   - LLM: Heuristic (30% follow if not following, 10% unfollow if following)
3. Create FOLLOW or UNFOLLOW action in Follow table

**Configuration**: Global via `probability_of_secondary_follow` in simulation_config.json

**Use Case**: Model organic network growth through content discovery

### 4. Daily Follow Evaluation

At the end of each simulation day, active agents evaluate new follow relationships.

**Architecture**:
```
Track active agents → End of day → Evaluate with probability → Get suggestions → Select candidate → FOLLOW
```

**Process**:
1. Track all agents active during each simulation day
2. At day end (last time slot), for each active agent:
   - With probability `daily_follow`, evaluate new follows
   - Request top-10 suggestions using agent's `frecsys_type`
   - Randomly select one candidate from suggestions
3. Create FOLLOW action in Follow table

**Configuration**: Global via `probability_of_daily_follow` in simulation_config.json

**Timing**: Evaluated when transitioning to next day (slot 23 → day+1)

**Use Case**: Model gradual network growth independent of content interactions

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
- ✅ Compute content recommendations (posts to read)
- ✅ Compute follow recommendations (users to follow)
- ✅ Execute follow recommendation algorithms (query-based)

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
- ✅ Request content recommendations
- ✅ Request follow recommendations
- ✅ Evaluate secondary follow (after interactions)
- ✅ Evaluate daily follows (at end of each day)
- ✅ Track active agents per day
- ✅ Select action types based on agent archetypes
- ✅ Apply agent_downcast override to force rule-based behavior for validators and explorers

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
- [Opinion Dynamics](OPINION_DYNAMICS.md)
- [Extension Guide](EXTENDING.md)
- [Redis Integration](RECSYS_REDIS_SUPPORT.md)
- [Code Formatting](FORMATTING.md)
