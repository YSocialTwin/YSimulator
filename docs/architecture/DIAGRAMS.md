# YSimulator System Diagrams

This document contains visual representations of the YSimulator system architecture and interaction patterns.

## Table of Contents
- [System Architecture](#system-architecture)
- [Component Interaction](#component-interaction)
- [Data Flow](#data-flow)
- [Sequence Diagrams](#sequence-diagrams)
- [State Diagrams](#state-diagrams)

## System Architecture

### Overall System Structure

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                            YSimulator System                                   ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                                 ║
║  ┌───────────────────┐         ┌───────────────────┐                          ║
║  │   Client 1        │         │   Client 2        │        ...Client N       ║
║  │ (Ray Actor)       │         │ (Ray Actor)       │                          ║
║  ├───────────────────┤         ├───────────────────┤                          ║
║  │                   │         │                   │                          ║
║  │ Agent Population  │         │ Agent Population  │                          ║
║  │ ┌───┐ ┌───┐ ┌───┐│         │ ┌───┐ ┌───┐ ┌───┐│                          ║
║  │ │ A │ │ A │ │ A ││         │ │ A │ │ A │ │ A ││                          ║
║  │ └───┘ └───┘ └───┘│         │ └───┘ └───┘ └───┘│                          ║
║  │                   │         │                   │                          ║
║  │ ┌─────────────┐   │         │ ┌─────────────┐   │                          ║
║  │ │ LLM Service │   │         │ │ LLM Service │   │                          ║
║  │ └─────────────┘   │         │ └─────────────┘   │                          ║
║  │                   │         │                   │                          ║
║  │ • start_day: 10   │         │ • start_day: 15   │                          ║
║  │ • max_day: 13     │         │ • max_day: 20     │                          ║
║  │ • heartbeat: 5s   │         │ • heartbeat: 5s   │                          ║
║  └─────────┬─────────┘         └─────────┬─────────┘                          ║
║            │                             │                                     ║
║            │  Ray Remote Calls           │                                     ║
║            │  (register, get_instruction,│                                     ║
║            │   submit_action, heartbeat) │                                     ║
║            │                             │                                     ║
║            └──────────────┬──────────────┘                                     ║
║                           │                                                     ║
║                ┌──────────▼───────────┐                                        ║
║                │                      │                                         ║
║                │  OrchestratorServer  │                                         ║
║                │    (Ray Actor)       │                                         ║
║                ├──────────────────────┤                                         ║
║                │                      │                                         ║
║                │ State:               │                                         ║
║                │ • current_day: 16    │                                         ║
║                │ • current_slot: 3    │                                         ║
║                │ • registered: {C1,C2}│                                         ║
║                │ • completed: {}      │                                         ║
║                │ • barrier: 0/2       │                                         ║
║                │                      │                                         ║
║                │ ┌─────────────────┐  │                                         ║
║                │ │ Barrier Sync    │  │                                         ║
║                │ │ • Wait for all  │  │                                         ║
║                │ │ • Advance time  │  │                                         ║
║                │ └─────────────────┘  │                                         ║
║                │                      │                                         ║
║                │ ┌─────────────────┐  │                                         ║
║                │ │ Heartbeat Track │  │                                         ║
║                │ │ • Detect stale  │  │                                         ║
║                │ │ • Auto-remove   │  │                                         ║
║                │ └─────────────────┘  │                                         ║
║                │                      │                                         ║
║                │ ┌─────────────────┐  │                                         ║
║                │ │Database         │  │                                         ║
║                │ │Middleware       │  │                                         ║
║                │ └────────┬────────┘  │                                         ║
║                └─────────┬┴───────────┘                                         ║
║                          │                                                      ║
║                          │                                                      ║
║           ┌──────────────┼──────────────────┐                                  ║
║           │              │                  │                                   ║
║      ┌────▼─────┐   ┌───▼────────┐   ┌────▼─────┐                             ║
║      │  Redis   │   │  SQLite    │   │PostgreSQL│   MySQL                     ║
║      │  Cache   │   │  Database  │   │ Database │                             ║
║      │          │   │            │   │          │                             ║
║      │ • Recent │   │ • All Data │   │ • All Data│                             ║
║      │   Data   │   │ • Durable  │   │ • Durable │                             ║
║      │ • Fast   │   │            │   │           │                             ║
║      └──────────┘   └────────────┘   └──────────┘                             ║
║                                                                                 ║
╚═════════════════════════════════════════════════════════════════════════════════╝
```

### Client Internal Structure

```
┌─────────────────────────────────────────────────────────────┐
│              SimulationClient (Ray Actor)                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Entry Point from Server:                                   │
│  ┌──────────────────────────────────────────────────┐       │
│  │ register_client() → {start_day: 10, start_slot: 0}│       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  Local State:                                                │
│  ┌──────────────────────────────────────────────────┐       │
│  │ • start_day = 10                                 │       │
│  │ • max_day = start_day + num_days = 13           │       │
│  │ • heartbeat_interval = 5 seconds                │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │           Main Simulation Loop                   │       │
│  │                                                  │       │
│  │  while True:                                     │       │
│  │    ┌─────────────────────────────────────────┐  │       │
│  │    │ 1. Check: current_day >= max_day?      │  │       │
│  │    │    → Yes: Exit                          │  │       │
│  │    └─────────────────────────────────────────┘  │       │
│  │    ┌─────────────────────────────────────────┐  │       │
│  │    │ 2. Get instruction from server          │  │       │
│  │    │    → WAIT: Sleep and retry              │  │       │
│  │    │    → PROCEED: Continue                  │  │       │
│  │    └─────────────────────────────────────────┘  │       │
│  │    ┌─────────────────────────────────────────┐  │       │
│  │    │ 3. Execute slot actions                 │  │       │
│  │    │    ┌─────────────────────────────────┐  │  │       │
│  │    │    │ For each agent:                 │  │  │       │
│  │    │    │  • Decide action                │  │  │       │
│  │    │    │  • Generate content (LLM)       │  │  │       │
│  │    │    │  • Submit to server             │  │  │       │
│  │    │    └─────────────────────────────────┘  │  │       │
│  │    └─────────────────────────────────────────┘  │       │
│  │    ┌─────────────────────────────────────────┐  │       │
│  │    │ 4. Submit completion (barrier++)        │  │       │
│  │    └─────────────────────────────────────────┘  │       │
│  │    ┌─────────────────────────────────────────┐  │       │
│  │    │ 5. Send heartbeat                       │  │       │
│  │    └─────────────────────────────────────────┘  │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │           Agent Population                       │       │
│  │  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐            │       │
│  │  │Agent│  │Agent│  │Agent│  │Agent│  ...        │       │
│  │  │  1  │  │  2  │  │  3  │  │  4  │            │       │
│  │  └─────┘  └─────┘  └─────┘  └─────┘            │       │
│  │  Each with:                                      │       │
│  │  • Personality (Big Five)                        │       │
│  │  • Demographics                                  │       │
│  │  • Behavior profile                              │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │           LLM Service                            │       │
│  │  • Address: http://llm:11434                     │       │
│  │  • Model: llama3                                 │       │
│  │  • Temperature: 0.7                              │       │
│  │  • Prompts: Per-cluster templates                │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │           Logging                                │       │
│  │  • JSON format                                   │       │
│  │  • Rotating files (10MB, 5 backups)              │       │
│  │  • Execution times tracked                       │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Server Internal Structure

```
┌──────────────────────────────────────────────────────────────┐
│           OrchestratorServer (Ray Actor)                      │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Temporal State:                                              │
│  ┌───────────────────────────────────────────────────┐       │
│  │ current_day: 16        current_slot: 3            │       │
│  │ slots_per_day: 24                                 │       │
│  └───────────────────────────────────────────────────┘       │
│                                                               │
│  Client State:                                                │
│  ┌───────────────────────────────────────────────────┐       │
│  │ registered_clients: {"client1", "client2"}        │       │
│  │ completed_clients: {}                             │       │
│  │ active_clients: registered - completed            │       │
│  │ last_heartbeat: {"client1": t1, "client2": t2}   │       │
│  └───────────────────────────────────────────────────┘       │
│                                                               │
│  Synchronization:                                             │
│  ┌───────────────────────────────────────────────────┐       │
│  │ barrier_counter: 1/2                              │       │
│  │ min_to_start: 1                                   │       │
│  │ timeout_seconds: 60                               │       │
│  └───────────────────────────────────────────────────┘       │
│                                                               │
│  ┌──────────────────────────────────────────────────┐        │
│  │          Core Methods                            │        │
│  │                                                  │        │
│  │  register_client(client_id, num_days)           │        │
│  │  ├─→ Add to registered_clients                  │        │
│  │  ├─→ Initialize last_heartbeat[client_id]       │        │
│  │  └─→ Return {start_day, start_slot}             │        │
│  │                                                  │        │
│  │  get_instruction(client_id)                     │        │
│  │  ├─→ Check for stale clients                    │        │
│  │  ├─→ Check barrier                              │        │
│  │  │   ├─ All submitted? → PROCEED, advance time  │        │
│  │  │   └─ Waiting? → WAIT                         │        │
│  │  └─→ Return {status, day, slot}                 │        │
│  │                                                  │        │
│  │  submit_action(client_id, action_data)          │        │
│  │  ├─→ Add temporal context (day, slot)           │        │
│  │  ├─→ DatabaseServiceAdapter.add_post()          │        │
│  │  └─→ Return {success, id}                       │        │
│  │                                                  │        │
│  │  submit_completion(client_id)                   │        │
│  │  ├─→ Increment barrier_counter                  │        │
│  │  └─→ Log submission                             │        │
│  │                                                  │        │
│  │  heartbeat(client_id)                           │        │
│  │  └─→ Update last_heartbeat[client_id] = now()   │        │
│  │                                                  │        │
│  │  complete_client(client_id)                     │        │
│  │  ├─→ Add to completed_clients                   │        │
│  │  ├─→ Update active_clients                      │        │
│  │  └─→ Log completion                             │        │
│  └──────────────────────────────────────────────────┘        │
│                                                               │
│  ┌──────────────────────────────────────────────────┐        │
│  │      Barrier Synchronization Logic               │        │
│  │                                                  │        │
│  │  Before returning instruction:                   │        │
│  │  1. Check for stale clients                      │        │
│  │     └─→ Remove if no heartbeat > timeout         │        │
│  │  2. Count submissions                            │        │
│  │     └─→ barrier_counter vs len(active_clients)   │        │
│  │  3. If all submitted:                            │        │
│  │     ├─→ Advance time (slot++, day++ if needed)   │        │
│  │     ├─→ Reset barrier_counter = 0                │        │
│  │     ├─→ Consolidate if day changed (Redis)       │        │
│  │     └─→ Return PROCEED                           │        │
│  │  4. Else:                                        │        │
│  │     └─→ Return WAIT                              │        │
│  └──────────────────────────────────────────────────┘        │
│                                                               │
│  ┌──────────────────────────────────────────────────┐        │
│  │      Database Middleware                         │        │
│  │  ┌──────────────────────────────────────────┐   │        │
│  │  │ register_user(agent_profile)             │   │        │
│  │  │ add_post(post_data) → post_id            │   │        │
│  │  │ add_interaction(interaction_data) → id   │   │        │
│  │  │ get_user(user_id) → profile              │   │        │
│  │  │ get_recent_posts(user_id, limit) → []    │   │        │
│  │  │ consolidate_day(day)                     │   │        │
│  │  └──────────────────────────────────────────┘   │        │
│  │                                                  │        │
│  │  Storage Strategy:                               │        │
│  │  ├─→ Redis: Write if enabled (cache)             │        │
│  │  └─→ SQL: Always write (persistence)             │        │
│  └──────────────────────────────────────────────────┘        │
│                                                               │
│  ┌──────────────────────────────────────────────────┐        │
│  │      Logging                                     │        │
│  │  • server.log: Main server process               │        │
│  │  • actor.log: Orchestrator actor operations      │        │
│  │  • JSON format with execution times              │        │
│  └──────────────────────────────────────────────────┘        │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

## Component Interaction

### Client-Server Communication

```
Client                                Server
  │                                     │
  │ 1. register_client(id, num_days)   │
  ├────────────────────────────────────>│
  │                                     │ Store registration
  │                                     │ Initialize heartbeat
  │    {start_day: 10, start_slot: 0}  │
  │<────────────────────────────────────┤
  │                                     │
  │                                     │
  │ 2. get_instruction(id)              │
  ├────────────────────────────────────>│
  │                                     │ Check stale clients
  │                                     │ Check barrier
  │    {status: "WAIT", day: 10, slot: 0}
  │<────────────────────────────────────┤
  │                                     │
  │ Sleep...                            │
  │                                     │
  │ 3. get_instruction(id)              │
  ├────────────────────────────────────>│
  │                                     │ Barrier complete!
  │                                     │ Advance time
  │    {status: "PROCEED", day: 10, slot: 1}
  │<────────────────────────────────────┤
  │                                     │
  │                                     │
  │ Execute actions...                  │
  │                                     │
  │                                     │
  │ 4. submit_action(id, post_data)     │
  ├────────────────────────────────────>│
  │                                     │ Add temporal context
  │                                     │ Store via middleware
  │    {success: true, post_id: "..."}  │
  │<────────────────────────────────────┤
  │                                     │
  │                                     │
  │ 5. submit_completion(id)            │
  ├────────────────────────────────────>│
  │                                     │ Increment barrier
  │    {success: true}                  │
  │<────────────────────────────────────┤
  │                                     │
  │                                     │
  │ 6. heartbeat(id)                    │
  ├────────────────────────────────────>│
  │                                     │ Update timestamp
  │    {success: true}                  │
  │<────────────────────────────────────┤
  │                                     │
  │ Loop continues...                   │
  │                                     │
  │ Eventually...                       │
  │                                     │
  │ 7. complete_client(id)              │
  ├────────────────────────────────────>│
  │                                     │ Add to completed
  │                                     │ Update active_clients
  │    {success: true}                  │
  │<────────────────────────────────────┤
  │                                     │
  │ Exit simulation                     │
  │                                     │
```

### Multi-Client Barrier Synchronization

```
Time: t0 (Server: day 10, slot 0, barrier: 0/2)

Client 1                Server                  Client 2
   │                      │                        │
   │ get_instruction()    │                        │
   ├─────────────────────>│                        │
   │                      │ Check: barrier 0/2     │
   │     WAIT             │                        │
   │<─────────────────────┤                        │
   │                      │                        │
   │                      │    get_instruction()   │
   │                      │<───────────────────────┤
   │                      │ Check: barrier 0/2     │
   │                      │     WAIT               │
   │                      ├───────────────────────>│
   │                      │                        │
   │ execute slot 0       │                        │ execute slot 0
   │                      │                        │
   │ submit_completion()  │                        │
   ├─────────────────────>│                        │
   │                      │ barrier: 1/2           │
   │     success          │                        │
   │<─────────────────────┤                        │
   │                      │                        │
   │ get_instruction()    │                        │
   ├─────────────────────>│                        │
   │                      │ Check: barrier 1/2     │
   │     WAIT             │                        │
   │<─────────────────────┤                        │
   │                      │                        │
   │                      │  submit_completion()   │
   │                      │<───────────────────────┤
   │                      │ barrier: 2/2 ✓         │
   │                      │ Advance: slot 0 → 1    │
   │                      │ Reset barrier: 0/2     │
   │                      │     success            │
   │                      ├───────────────────────>│
   │                      │                        │
   │ get_instruction()    │                        │
   ├─────────────────────>│                        │
   │                      │ Check: barrier 0/2     │
   │     PROCEED          │                        │
   │     day:10, slot:1   │                        │
   │<─────────────────────┤                        │
   │                      │                        │
   │                      │    get_instruction()   │
   │                      │<───────────────────────┤
   │                      │ Check: barrier 0/2     │
   │                      │     PROCEED            │
   │                      │     day:10, slot:1     │
   │                      ├───────────────────────>│
   │                      │                        │
   │ execute slot 1       │                        │ execute slot 1
   │                      │                        │
```

## Data Flow

### Action Submission Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                    Action Submission Flow                         │
└──────────────────────────────────────────────────────────────────┘

Agent Decides to Post
        │
        │ 1. Generate Content
        ▼
┌────────────────┐
│  LLM Service   │
│                │
│ • Select prompt template (by cluster)
│ • Apply persona (personality traits)
│ • Call LLM API
│ • Return generated content
└───────┬────────┘
        │
        │ 2. Submit to Server
        ▼
┌─────────────────────────────────────┐
│    Client.submit_action()           │
│                                     │
│  action_data = {                    │
│    "type": "post",                  │
│    "user_id": agent.id,             │
│    "content": generated_content,    │
│    "likes": 0                       │
│  }                                  │
└───────┬─────────────────────────────┘
        │
        │ Ray Remote Call
        ▼
┌─────────────────────────────────────┐
│  Server.submit_action()             │
│                                     │
│  • Add temporal context:            │
│    action_data["day"] = current_day │
│    action_data["slot"] = current_slot│
│  • Generate UUID for post           │
│  • Call middleware                  │
└───────┬─────────────────────────────┘
        │
        │
        ▼
┌─────────────────────────────────────┐
│  PostService.add_post()             │
│  (via DatabaseServiceAdapter)       │
│                                     │
│  1. Generate UUID for post          │
│  2. Add metadata (timestamp, etc)   │
│  3. Call PostRepository             │
│                                     │
│  PostRepository.add_post()          │
│  ├─→ If Redis: Store in Redis      │
│  │   redis.lpush("posts:recent",...)│
│  └─→ Store in SQL via SQLAlchemy   │
│      ├─→ Create Post model          │
│      ├─→ session.add(post)          │
│     └─→ session.commit()            │
└───────┬─────────────────────────────┘
        │
        │ Return post_id
        ▼
┌─────────────────────────────────────┐
│  Client receives response           │
│  {success: true, post_id: "..."}    │
│                                     │
│  • Log action                       │
│  • Continue with next action        │
└─────────────────────────────────────┘
```

### Daily Consolidation Flow (Redis → SQL)

```
┌──────────────────────────────────────────────────────────────┐
│              Daily Consolidation Flow                         │
└──────────────────────────────────────────────────────────────┘

Server advances to new day
        │
        │ Trigger: current_slot == 0 AND day changed
        ▼
┌─────────────────────────────────────┐
│  Server.advance_time()              │
│                                     │
│  if Redis enabled:                  │
│    (Note: Redis consolidation handled at repository layer)    │
└───────┬────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  Repository Layer handles data persistence          │
│                                                     │
│  SQL repositories maintain data in database         │
│  Redis repositories cache for performance           │
│  Both accessed through service layer                │
│                                                     │
│  3. Get all interaction IDs for the day            │
│     int_ids = redis.smembers("interactions:day:{day}")│
│                                                     │
│  4. For each interaction:                          │
│     ├─→ Fetch data: redis.hgetall("interaction:{id}")│
│     ├─→ Create InteractionModel                    │
│     ├─→ session.merge(interaction)                 │
│     └─→ Count++                                    │
│                                                     │
│  5. Commit all to SQL                              │
│     session.commit()                               │
│                                                     │
│  6. Remove old data from Redis                     │
│     cutoff_day = current_day - sliding_window_days │
│     For day < cutoff_day:                          │
│       ├─→ Get old_post_ids                         │
│       ├─→ For each: redis.delete("post:{id}")      │
│       ├─→ redis.delete("posts:day:{day}")          │
│       ├─→ Same for interactions                    │
│       └─→ Count removed++                          │
│                                                     │
│  7. Log metrics                                    │
│     • Posts saved: X                               │
│     • Interactions saved: Y                        │
│     • Old posts removed: Z                         │
│     • Execution time: T ms                         │
└─────────────────────────────────────────────────────┘
```

## Sequence Diagrams

### Simulation Startup Sequence

```
run_server          Ray         OrchestratorServer    Service Layer         Storage
     │               │                  │                     │               │
     │ 1. Load config│                  │                     │               │
     ├───────────────┤                  │                     │               │
     │               │                  │                     │               │
     │ 2. init(...)  │                  │                     │               │
     ├──────────────>│                  │                     │               │
     │               │                  │                     │               │
     │               │ 3. Create Actor  │                     │               │
     │               ├─────────────────>│                     │               │
     │               │                  │                     │               │
     │               │                  │ 4. __init__()        │               │
     │               │                  ├─────────────────────>│               │
     │               │                  │                      │               │
     │               │                  │                      │ 5. Connect    │
     │               │                  │                      ├──────────────>│
     │               │                  │                      │               │
     │               │                  │                      │ 6. Test conn  │
     │               │                  │                      │<──────────────┤
     │               │                  │                      │               │
     │               │                  │ 7. Middleware ready  │               │
     │               │                  │<─────────────────────┤               │
     │               │                  │                      │               │
     │               │ 8. Actor ready   │                      │               │
     │               │<─────────────────┤                      │               │
     │               │                  │                      │               │
     │ 9. Server ref │                  │                      │               │
     │<──────────────┤                  │                      │               │
     │               │                  │                      │               │
     │ 10. Wait for min_to_start clients│                      │               │
     │               │                  │                      │               │


run_client          Ray         SimulationClient       Server            LLMService
     │               │                  │                │                  │
     │ 1. Load configs│                 │                │                  │
     ├───────────────┤                  │                │                  │
     │               │                  │                │                  │
     │ 2. init(...)  │                  │                │                  │
     ├──────────────>│                  │                │                  │
     │               │                  │                │                  │
     │               │ 3. Create Actor  │                │                  │
     │               ├─────────────────>│                │                  │
     │               │                  │                │                  │
     │               │                  │ 4. register()  │                  │
     │               │                  ├───────────────>│                  │
     │               │                  │                │                  │
     │               │                  │ 5. {start_day} │                  │
     │               │                  │<───────────────┤                  │
     │               │                  │                │                  │
     │               │                  │ 6. register_agents()             │
     │               │                  ├───────────────>│                  │
     │               │                  │                │ Store in DB      │
     │               │                  │                │                  │
     │               │                  │ 7. Initialize LLMService          │
     │               │                  ├──────────────────────────────────>│
     │               │                  │                │                  │
     │               │                  │ 8. Test connection                │
     │               │                  │<──────────────────────────────────┤
     │               │                  │                │                  │
     │               │ 9. Actor ready   │                │                  │
     │               │<─────────────────┤                │                  │
     │               │                  │                │                  │
     │ 10. Client ref│                  │                │                  │
     │<──────────────┤                  │                │                  │
     │               │                  │                │                  │
     │ 11. Start run()│                 │                │                  │
     │               │                  │ Begin simulation loop...           │
     │               │                  │                │                  │
```

### Client Completion and Restart

```
Client A                      Server                    Client A (Restarted)
(Start: day 10, run 3 days)                             
     │                          │                              │
     │ Running days 10-12...    │                              │
     │                          │                              │
     │ Day 13: Exit condition   │                              │
     │                          │                              │
     │ complete_client("A")     │                              │
     ├─────────────────────────>│                              │
     │                          │ Add to completed_clients     │
     │                          │ Update active_clients        │
     │     success              │                              │
     │<─────────────────────────┤                              │
     │                          │                              │
     │ Exit                     │                              │
     │                          │                              │
     │                          │ Server continues at day 20   │
     │                          │                              │
     │                          │                              │
     │                          │  register_client("A", 3)     │
     │                          │<─────────────────────────────┤
     │                          │                              │
     │                          │ Remove from completed        │
     │                          │ Add to registered            │
     │                          │ start_day = 20 (current!)    │
     │                          │                              │
     │                          │  {start_day: 20, start_slot: 0}
     │                          ├─────────────────────────────>│
     │                          │                              │
     │                          │                              │ Calculate:
     │                          │                              │ max_day = 20 + 3 = 23
     │                          │                              │
     │                          │                              │ Run days 20-22
     │                          │                              │
```

## State Diagrams

### Client State Machine

```
┌──────────────────────────────────────────────────────────────┐
│                  Client State Machine                         │
└──────────────────────────────────────────────────────────────┘

                    ┌─────────────┐
                    │   START     │
                    └──────┬──────┘
                           │
                           │ Load config
                           ▼
                    ┌─────────────┐
                    │ REGISTERING │
                    └──────┬──────┘
                           │
                           │ register_client()
                           │ → Receive start_day
                           ▼
                    ┌─────────────┐
                    │  RUNNING    │◄────────────┐
                    └──────┬──────┘             │
                           │                    │
                           │ Each iteration:     │
                           │                    │
                ┌──────────┴──────────┐         │
                │                     │         │
                ▼                     ▼         │
         ┌─────────────┐      ┌─────────────┐  │
         │ Check Exit  │      │ Get Instruc │  │
         │ current_day │      │   tion      │  │
         │ >= max_day? │      └──────┬──────┘  │
         └──────┬──────┘             │         │
                │                    │         │
                │ Yes                │         │
                │                    ▼         │
                │             ┌─────────────┐  │
                │             │   status?   │  │
                │             └──────┬──────┘  │
                │                    │         │
                │                    ├─ WAIT ──┘
                │                    │ (sleep)
                │                    │
                │                    ├─ PROCEED
                │                    ▼
                │             ┌─────────────┐
                │             │  Execute    │
                │             │  Actions    │
                │             └──────┬──────┘
                │                    │
                │                    │ Submit completion
                │                    │ Send heartbeat
                │                    └────────┘
                │
                ▼
         ┌─────────────┐
         │ COMPLETING  │
         └──────┬──────┘
                │
                │ complete_client()
                ▼
         ┌─────────────┐
         │   EXITED    │
         └─────────────┘
```

### Server Barrier State Machine

```
┌──────────────────────────────────────────────────────────────┐
│               Server Barrier State Machine                    │
└──────────────────────────────────────────────────────────────┘

For each time slot:

                ┌─────────────────┐
                │  WAITING FOR    │
                │  SUBMISSIONS    │
                │                 │
                │ barrier: 0/N    │
                └────────┬────────┘
                         │
                         │ Client calls get_instruction()
                         │
                         ▼
                ┌──────────────────┐
                │ Check for Stale  │
                │    Clients       │
                └────────┬─────────┘
                         │
                         │ Remove clients with no heartbeat
                         │ Update active_clients
                         │
                         ▼
                ┌──────────────────┐
                │  Check Barrier   │
                │                  │
                │ submitted ==     │
                │ active_clients?  │
                └────────┬─────────┘
                         │
                    ┌────┴────┐
                    │         │
                 No │         │ Yes
                    │         │
                    ▼         ▼
            ┌───────────┐  ┌────────────┐
            │  Return   │  │  Advance   │
            │   WAIT    │  │   Time     │
            └───────────┘  └─────┬──────┘
                    │              │
                    │              │ slot++
                    │              │ If slot >= slots_per_day:
                    │              │   day++
                    │              │   slot = 0
                    │              │   consolidate_day() if Redis
                    │              │
                    │              │ barrier = 0
                    │              │
                    │              ▼
                    │         ┌────────────┐
                    │         │  Return    │
                    │         │  PROCEED   │
                    │         └────────────┘
                    │              │
                    └──────────────┴───────────┐
                                              │
                                              │
                                              ▼
                                   ┌──────────────────┐
                                   │ Clients Process  │
                                   │   New Slot       │
                                   └──────────────────┘
```

## Conclusion

These diagrams illustrate:

1. **System Architecture**: Overall structure and component relationships
2. **Internal Structure**: Detailed view of client and server internals
3. **Communication**: How clients and servers interact via Ray
4. **Synchronization**: Multi-client barrier coordination
5. **Data Flow**: How actions move from agents to storage
6. **Sequences**: Temporal ordering of operations
7. **States**: Client and server state transitions

For textual descriptions and implementation details, see:
- [Architecture Documentation](ARCHITECTURE.md)
- [Extension Guide](../development/EXTENDING.md)
- [Configuration Guide](../configuration/CONFIG.md)
