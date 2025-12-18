# Extending YSimulator: Adding New Agent Actions

This guide explains how to extend the YSimulator framework by adding new agent actions to the client and server.

## Table of Contents
- [Overview](#overview)
- [Architecture Review](#architecture-review)
- [Adding a New Action: Step by Step](#adding-a-new-action-step-by-step)
- [Example: Adding a "Share" Action](#example-adding-a-share-action)
- [Testing Your Extension](#testing-your-extension)
- [Best Practices](#best-practices)

## Overview

YSimulator uses a **distributed actor model** built on Ray. Agent actions are:
1. **Initiated** by the client (simulation actors)
2. **Coordinated** through the server (orchestrator)
3. **Stored** in the database middleware

Adding a new action requires modifications to:
- **Client Side**: Agent logic and action execution
- **Server Side**: Action handling and storage
- **Data Models**: Database schema and Ray message types

## Architecture Review

### Client Architecture
```
SimulationClient (Ray Actor)
├── run() - Main simulation loop
├── _execute_slot() - Execute one time slot
├── _perform_agent_actions() - Coordinate agent actions
└── Agent instances - Individual agent logic
```

### Server Architecture
```
OrchestratorServer (Ray Actor)
├── get_instruction() - Provide time coordination
├── submit_action() - Receive and process actions
├── register_agents() - Store agent profiles
└── DatabaseMiddleware - Abstract storage layer
```

### Action Flow
```
Client Agent → submit_action() → Server → DatabaseMiddleware → Database
                                    ↓
                              Consolidation (if Redis)
```

## Adding a New Action: Step by Step

### Step 1: Define the Action Model

Create or update the database model in `classes/models.py`:

```python
from sqlalchemy import Column, Integer, String, Text, ForeignKey

class ShareModel(db.Model):
    """Model for share actions."""
    __tablename__ = "shares"
    __bind_key__ = "db_exp"
    
    id = db.Column(db.String(36), primary_key=True)  # UUID
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    post_id = db.Column(db.String(36), db.ForeignKey("posts.id"), nullable=False)
    share_comment = db.Column(db.Text, nullable=True)
    day = db.Column(db.Integer, nullable=False)
    slot = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.Integer, nullable=False)
```

**Key Points:**
- Use UUID (String 36) for new record IDs
- Include `day` and `slot` for temporal tracking
- Add foreign keys to relate to other entities
- Use appropriate data types (Text for long content, String for short)

### Step 2: Update Database Middleware

Add methods to `classes/db_middleware.py`:

```python
def add_share(self, share_data: dict) -> str:
    """
    Add a share action to the database.
    
    Args:
        share_data: Dictionary with keys: user_id, post_id, share_comment, day, slot
        
    Returns:
        share_id: UUID of the created share
    """
    import uuid
    share_id = str(uuid.uuid4())
    
    if self.use_redis:
        # Store in Redis
        share_key = f"share:{share_id}"
        self.redis_client.hset(share_key, mapping={
            "id": share_id,
            "user_id": share_data["user_id"],
            "post_id": share_data["post_id"],
            "share_comment": share_data.get("share_comment", ""),
            "day": share_data["day"],
            "slot": share_data["slot"],
            "timestamp": int(time.time())
        })
        # Add to day index for consolidation
        self.redis_client.sadd(f"shares:day:{share_data['day']}", share_id)
    
    # Always store in SQL for persistence
    share = ShareModel(
        id=share_id,
        user_id=share_data["user_id"],
        post_id=share_data["post_id"],
        share_comment=share_data.get("share_comment", ""),
        day=share_data["day"],
        slot=share_data["slot"],
        timestamp=int(time.time())
    )
    self.session.add(share)
    self.session.commit()
    
    return share_id
```

**Key Points:**
- Generate UUID for new records
- Store in both Redis (if enabled) and SQL
- Index by day in Redis for consolidation
- Include comprehensive logging

### Step 3: Add Consolidation Support

Update `consolidate_day()` in `classes/db_middleware.py`:

```python
def consolidate_day(self, current_day: int):
    """Consolidate data from Redis to SQL database."""
    if not self.use_redis:
        return
    
    # ... existing post/interaction consolidation ...
    
    # Consolidate shares
    share_key = f"shares:day:{current_day}"
    share_ids = self.redis_client.smembers(share_key)
    
    for share_id in share_ids:
        share_data = self.redis_client.hgetall(f"share:{share_id}")
        if share_data:
            share = ShareModel(
                id=share_data["id"],
                user_id=int(share_data["user_id"]),
                post_id=share_data["post_id"],
                share_comment=share_data.get("share_comment", ""),
                day=int(share_data["day"]),
                slot=int(share_data["slot"]),
                timestamp=int(share_data["timestamp"])
            )
            self.session.merge(share)  # Use merge to handle duplicates
    
    self.session.commit()
```

### Step 4: Add Server Handler

Update `YServer/server.py` to handle the new action:

```python
def submit_share(self, client_id: str, share_data: dict) -> dict:
    """
    Process a share action from a client.
    
    Args:
        client_id: ID of the submitting client
        share_data: Share information (user_id, post_id, share_comment)
        
    Returns:
        Response with share_id and status
    """
    start_time = time.time()
    
    try:
        # Add temporal context
        share_data["day"] = self.current_day
        share_data["slot"] = self.current_slot
        
        # Store via middleware
        share_id = self.db_middleware.add_share(share_data)
        
        execution_time = (time.time() - start_time) * 1000
        self.logger.info(
            "Share submitted",
            extra={
                "client_id": client_id,
                "share_id": share_id,
                "user_id": share_data["user_id"],
                "post_id": share_data["post_id"],
                "execution_time_ms": execution_time
            }
        )
        
        return {"success": True, "share_id": share_id}
        
    except Exception as e:
        self.logger.error(f"Error submitting share: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
```

**Key Points:**
- Add temporal context (day, slot) automatically
- Use middleware for storage abstraction
- Log with execution time metrics
- Return structured response

### Step 5: Implement Client-Side Logic

Add agent action in your agent class or `YClient/client.py`:

```python
def share_post(self, agent_id: int, post_id: str, comment: str = ""):
    """
    Agent shares a post with optional comment.
    
    Args:
        agent_id: ID of the agent sharing
        post_id: ID of the post to share
        comment: Optional comment to add
    """
    try:
        share_data = {
            "user_id": agent_id,
            "post_id": post_id,
            "share_comment": comment
        }
        
        # Call server
        response = ray.get(self.server.submit_share.remote(
            self.client_id,
            share_data
        ))
        
        if response.get("success"):
            self.logger.info(
                f"Agent {agent_id} shared post {post_id}",
                extra={"share_id": response.get("share_id")}
            )
        else:
            self.logger.error(
                f"Failed to share post: {response.get('error')}"
            )
            
    except Exception as e:
        self.logger.error(f"Error sharing post: {e}", exc_info=True)
```

### Step 6: Integrate into Action Loop

Update `_perform_agent_actions()` in `YClient/client.py`:

```python
def _perform_agent_actions(self):
    """Execute actions for all agents in current time slot."""
    
    for agent in self.agents:
        # ... existing action logic ...
        
        # New share action
        if should_share_post(agent):  # Your logic here
            post_to_share = select_post_to_share(agent)  # Your logic
            comment = generate_share_comment(agent, post_to_share)  # Your logic
            self.share_post(agent.id, post_to_share.id, comment)
```

## Example: Adding a "Share" Action

Here's a complete minimal example:

### 1. Model (classes/models.py)
```python
class ShareModel(db.Model):
    __tablename__ = "shares"
    __bind_key__ = "db_exp"
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    post_id = db.Column(db.String(36), nullable=False)
    day = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.Integer, nullable=False)
```

### 2. Middleware (classes/db_middleware.py)
```python
def add_share(self, user_id: int, post_id: str, day: int) -> str:
    import uuid
    share_id = str(uuid.uuid4())
    share = ShareModel(
        id=share_id,
        user_id=user_id,
        post_id=post_id,
        day=day,
        timestamp=int(time.time())
    )
    self.session.add(share)
    self.session.commit()
    return share_id
```

### 3. Server (YServer/server.py)
```python
def submit_share(self, client_id: str, user_id: int, post_id: str) -> dict:
    share_id = self.db_middleware.add_share(user_id, post_id, self.current_day)
    return {"success": True, "share_id": share_id}
```

### 4. Client (YClient/client.py)
```python
def share_post(self, agent_id: int, post_id: str):
    response = ray.get(self.server.submit_share.remote(
        self.client_id, agent_id, post_id
    ))
    return response.get("success", False)
```

## Testing Your Extension

### 1. Database Migration
After adding models, create tables:
```bash
python
>>> from run_server import db
>>> db.create_all()
```

### 2. Unit Tests
Create tests for your new methods:
```python
def test_add_share():
    middleware = DatabaseMiddleware(...)
    share_id = middleware.add_share(
        user_id=1,
        post_id="post-123",
        day=5
    )
    assert share_id is not None
    assert len(share_id) == 36  # UUID length
```

### 3. Integration Tests
Test the full flow:
```python
def test_share_flow():
    # Start server
    server = OrchestratorServer.remote(...)
    
    # Submit share
    response = ray.get(server.submit_share.remote("client1", 1, "post-123"))
    assert response["success"]
    
    # Verify in database
    share = db.session.query(ShareModel).filter_by(
        id=response["share_id"]
    ).first()
    assert share is not None
```

### 4. End-to-End Test
Run a simulation with the new action:
```bash
# Terminal 1
python run_server.py --config example_conf/

# Terminal 2
python run_client.py --config example_conf/
```

Check logs in `example_conf/logs/` for your new action.

## Best Practices

### 1. Data Consistency
- **Always store in SQL** for durability
- **Optionally cache in Redis** for performance
- **Use UUIDs** for distributed ID generation
- **Include temporal info** (day, slot) for analysis

### 2. Error Handling
```python
try:
    result = perform_action()
    log_success(result)
    return {"success": True, "data": result}
except ValidationError as e:
    log_warning(e)
    return {"success": False, "error": "Invalid data"}
except Exception as e:
    log_error(e, exc_info=True)
    return {"success": False, "error": "Internal error"}
```

### 3. Logging
```python
self.logger.info(
    "Action completed",
    extra={
        "action_type": "share",
        "client_id": client_id,
        "user_id": user_id,
        "execution_time_ms": execution_time
    }
)
```

### 4. Performance
- **Batch operations** when possible
- **Use indexes** on frequently queried fields
- **Limit payload sizes** in Ray messages
- **Monitor execution times** in logs

### 5. Documentation
- **Document parameters** with type hints
- **Explain complex logic** with comments
- **Provide examples** in docstrings
- **Update this guide** with lessons learned

## Common Pitfalls

### 1. Forgetting Temporal Context
```python
# BAD - no day/slot info
share_data = {"user_id": 1, "post_id": "123"}

# GOOD - includes temporal context
share_data = {
    "user_id": 1,
    "post_id": "123",
    "day": self.current_day,
    "slot": self.current_slot
}
```

### 2. Not Using UUIDs
```python
# BAD - auto-increment can conflict in distributed systems
id = db.Column(db.Integer, primary_key=True, autoincrement=True)

# GOOD - UUID for distributed ID generation
id = db.Column(db.String(36), primary_key=True)
# Generate with: str(uuid.uuid4())
```

### 3. Ignoring Redis Consolidation
```python
# BAD - Redis data is lost when sliding window expires
def add_share(self, data):
    if self.use_redis:
        self.redis_client.hset(f"share:{id}", data)
    # Missing: SQL storage and day indexing

# GOOD - Always persist to SQL
def add_share(self, data):
    if self.use_redis:
        self.redis_client.hset(f"share:{id}", data)
        self.redis_client.sadd(f"shares:day:{day}", id)
    # Also store in SQL
    self.session.add(ShareModel(**data))
    self.session.commit()
```

### 4. Blocking the Event Loop
```python
# BAD - blocking call in async context
response = self.server.submit_action(data)  # Blocks!

# GOOD - use ray.get() for remote calls
response = ray.get(self.server.submit_action.remote(data))
```

## Conclusion

Adding new actions to YSimulator follows a consistent pattern:
1. Define the data model
2. Implement storage in middleware
3. Add server handler
4. Implement client logic
5. Test thoroughly

Follow the patterns established in existing actions (posts, interactions) and refer to this guide when adding new capabilities.

For questions or improvements to this guide, please open an issue on GitHub.
