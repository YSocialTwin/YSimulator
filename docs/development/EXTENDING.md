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

## Using the Repository Pattern (NEW)

YSimulator now supports the **Repository Pattern** for better separation of concerns and testability. This pattern is recommended for all new extensions.

### Benefits of Repository Pattern

1. **Testability**: Easy to mock repositories for unit testing
2. **Flexibility**: Swap SQL/Redis without changing business logic  
3. **Maintainability**: Clear separation between data access and business logic
4. **Extensibility**: Easy to add new storage backends

### Repository Pattern Architecture

```
Service Layer (Business Logic)
    ↓
Repository Layer (Data Access Abstraction)
    ↓
Storage Backend (SQL/Redis/etc.)
```

### Using Repositories in Extensions

When adding new actions with the Repository Pattern:

#### Option 1: Use Existing Services

```python
# In server.py
from YSimulator.YServer.services import PostService, UserService
from YSimulator.YServer.repositories import SQLPostRepository, SQLUserRepository

# Initialize repositories
post_repo = SQLPostRepository(engine, logger)
user_repo = SQLUserRepository(engine, logger)

# Create services
post_service = PostService(post_repo)
user_service = UserService(user_repo)

# Use in server methods
def submit_new_action(self, client_id: str, action_data: dict) -> dict:
    # Use service instead of direct database access
    result = post_service.create_post({
        "id": action_data["id"],
        "author": action_data["user_id"],  # Mapped to user_id automatically
        "text": action_data["content"],    # Mapped to tweet automatically
        "round": self.current_round
    })
    return {"success": True, "post_id": result}
```

#### Option 2: Extend Repository Layer

If you need custom data access patterns:

```python
# 1. Define interface in base_repository.py
class CustomActionRepository(ABC):
    """Repository for custom action data."""
    
    @abstractmethod
    def add_custom_action(self, action_data: Dict[str, Any]) -> str:
        """Add a custom action."""
        pass
    
    @abstractmethod
    def get_custom_actions(self, user_id: str) -> List[Dict[str, Any]]:
        """Get custom actions for a user."""
        pass

# 2. Implement SQL version in sql_repository.py
class SQLCustomActionRepository(CustomActionRepository):
    """SQL implementation of CustomActionRepository."""
    
    def __init__(self, engine: Engine, logger: Optional[logging.Logger] = None):
        self.engine = engine
        self.logger = logger or logging.getLogger(__name__)
    
    def add_custom_action(self, action_data: Dict[str, Any]) -> str:
        import uuid
        session = Session(self.engine)
        try:
            action_id = str(uuid.uuid4())
            action = CustomActionModel(
                id=action_id,
                user_id=action_data["user_id"],
                action_type=action_data["action_type"],
                timestamp=int(time.time())
            )
            session.add(action)
            session.commit()
            return action_id
        except Exception as e:
            self.logger.error(f"Error adding custom action: {e}")
            session.rollback()
            raise
        finally:
            session.close()
    
    def get_custom_actions(self, user_id: str) -> List[Dict[str, Any]]:
        session = Session(self.engine)
        try:
            actions = session.query(CustomActionModel).filter_by(
                user_id=user_id
            ).all()
            return [{"id": a.id, "type": a.action_type} for a in actions]
        finally:
            session.close()

# 3. Implement Redis version in redis_repository.py
class RedisCustomActionRepository(CustomActionRepository):
    """Redis implementation of CustomActionRepository."""
    
    def __init__(self, redis_client, logger: Optional[logging.Logger] = None):
        self.redis_client = redis_client
        self.logger = logger or logging.getLogger(__name__)
    
    def add_custom_action(self, action_data: Dict[str, Any]) -> str:
        import uuid
        action_id = str(uuid.uuid4())
        key = f"custom_action:{action_id}"
        self.redis_client.hset(key, mapping={
            "id": action_id,
            "user_id": action_data["user_id"],
            "action_type": action_data["action_type"],
            "timestamp": str(int(time.time()))
        })
        # Index by user for retrieval
        self.redis_client.sadd(f"user_actions:{action_data['user_id']}", action_id)
        return action_id
    
    def get_custom_actions(self, user_id: str) -> List[Dict[str, Any]]:
        action_ids = self.redis_client.smembers(f"user_actions:{user_id}")
        actions = []
        for action_id in action_ids:
            action_data = self.redis_client.hgetall(f"custom_action:{action_id}")
            if action_data:
                actions.append({
                    "id": action_data[b"id"].decode(),
                    "type": action_data[b"action_type"].decode()
                })
        return actions

# 4. Create service layer
class CustomActionService:
    """Service for custom action business logic."""
    
    def __init__(self, custom_action_repo: CustomActionRepository):
        self.repo = custom_action_repo
        self.logger = logging.getLogger(__name__)
    
    def record_action(self, user_id: str, action_type: str) -> Optional[str]:
        """Record a custom action."""
        try:
            action_id = self.repo.add_custom_action({
                "user_id": user_id,
                "action_type": action_type
            })
            self.logger.info(f"Custom action recorded: {action_id}")
            return action_id
        except Exception as e:
            self.logger.error(f"Failed to record action: {e}")
            return None
    
    def get_user_actions(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all actions for a user."""
        return self.repo.get_custom_actions(user_id)
```

### Field Name Mapping

The repository layer automatically handles field name mapping between API and database:

```python
# API uses friendly names
post_data = {
    "author": "user123",         # Maps to user_id in database
    "text": "Hello world",       # Maps to tweet in database
    "parent_post": "post456",    # Maps to comment_to in database
    "num_reactions": 5           # Maps to reaction_count in database
}

# Repository handles mapping automatically
post_repo.add_post(post_data)  # Stores with correct database field names
```

**Complete Mapping Table**:
| API Field | Database Field | Model |
|-----------|----------------|-------|
| `text` | `tweet` | Post |
| `author` | `user_id` | Post |
| `parent_post` | `comment_to` | Post |
| `root_post` | `thread_id` | Post |
| `num_reactions` | `reaction_count` | Post |
| `followee_id` | `user_id` | Follow |
| `round_id` | `tid` | Agent_Opinion |

### Testing with Repositories

The Repository Pattern makes testing much easier:

```python
import pytest
from unittest.mock import Mock
from YSimulator.YServer.services import CustomActionService

def test_record_action():
    # Mock the repository
    mock_repo = Mock()
    mock_repo.add_custom_action.return_value = "action123"
    
    # Create service with mock
    service = CustomActionService(mock_repo)
    
    # Test business logic
    action_id = service.record_action("user1", "click")
    
    # Verify
    assert action_id == "action123"
    mock_repo.add_custom_action.assert_called_once_with({
        "user_id": "user1",
        "action_type": "click"
    })
```

### Migration from DatabaseMiddleware

If you have existing code using DatabaseMiddleware, you can migrate gradually:

```python
# Old approach (still works)
share_id = self.db_middleware.add_share(share_data)

# New approach (recommended)
from YSimulator.YServer.services import PostService
from YSimulator.YServer.repositories import SQLPostRepository

post_repo = SQLPostRepository(engine, logger)
post_service = PostService(post_repo)
post_id = post_service.create_post(post_data)
```

Both approaches are fully supported for backward compatibility.

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

## Example: Image Sharing Action

The image sharing action demonstrates a complex action with multiple components: database queries, LLM interaction, and topic management.

### Overview

The image action allows agents to:
1. Randomly select an image from the images table
2. Retrieve topics from the associated article
3. Generate commentary using LLM (or use "IMAGE" text for rule-based agents)
4. Create a post with image_id reference
5. Link topics to the post

### Implementation Components

#### 1. Database Methods

```python
# In db_middleware.py

def get_random_image(self) -> Optional[Dict[str, Any]]:
    """Get a random image from the images table."""
    session = Session(self.engine)
    try:
        image = session.query(Image).order_by(func.random()).first()
        if image:
            return {
                "id": image.id,
                "url": image.url,
                "description": image.description,
                "article_id": image.article_id
            }
        return None
    finally:
        session.close()

def get_interest_by_id(self, interest_ids: List[str]) -> List[str]:
    """Retrieve topic names from topic IDs."""
    session = Session(self.engine)
    try:
        topics = session.query(Interest).filter(Interest.iid.in_(interest_ids)).all()
        return [topic.interest_name for topic in topics]
    finally:
        session.close()
```

#### 2. LLM Service Method

```python
# In llm_service.py

def generate_image_commentary(self, image_description: str, persona: str, toxicity: float, topics: List[str]) -> Optional[str]:
    """Generate social media commentary about an image."""
    prompt_config = self.prompts.get("generate_image_commentary", {})
    system_template = prompt_config.get("system_template", "{persona}")
    user_template = prompt_config.get("user_template", "Create a post about: {image_description}")
    
    # Format topics instruction
    topics_instruction = f"Mention these topics: {', '.join(topics)}" if topics else ""
    
    # Format templates
    system_prompt = system_template.format(persona=persona, toxicity=toxicity)
    user_prompt = user_template.format(
        image_description=image_description,
        topics_instruction=topics_instruction
    )
    
    response = self._call_llm(system_prompt, user_prompt)
    return response[:280] if response else None  # Limit to 280 chars
```

#### 3. Client Action Handler

```python
# In client.py

def _handle_image_action(self, agent, actions):
    """Handle image sharing action for an agent."""
    try:
        # 1. Get random image
        image_result = ray.get(self.server.get_random_image.remote())
        if not image_result:
            self.logger.info(f"No images available for agent {agent.username}")
            return
        
        image_id = image_result["id"]
        article_id = image_result["article_id"]
        
        # 2. Get topics from article
        topic_ids = ray.get(self.server.get_article_topics.remote(article_id))
        
        # 3. Generate post
        if agent.is_llm:
            # LLM generates commentary
            future = self.llm_service.generate_image_commentary_async.remote(
                image_description=image_result["description"],
                persona=agent.persona,
                toxicity=agent.toxicity,
                topics=topic_names
            )
            self.llm_pending_posts.append((agent.id, agent.cluster, future, None, image_id, topic_ids))
        else:
            # Rule-based uses "IMAGE" text
            action = generate_rule_based_image_post(agent.id, agent.cluster, image_id)
            action.topic_ids = topic_ids
            actions.append(action)
            
    except Exception as e:
        self.logger.error(f"Error handling image action: {e}")
```

#### 4. Server Handler

```python
# In server.py

# Add image_id to post_data
if hasattr(act, 'image_id') and act.image_id:
    post_data["image_id"] = act.image_id

# After post creation, link topics
if hasattr(act, 'topic_ids') and act.topic_ids:
    for topic_id in act.topic_ids:
        self.db.add_post_topic(post_id, topic_id)
```

### Configuration

```json
// In simulation_config.json
{
  "llm_v": {
    "address": "localhost",
    "port": 11434,
    "model": "minicpm-v",
    "temperature": 0.5
  },
  "agents": {
    "actions_likelihood": {
      "post": 0.3,
      "image": 0.1
    }
  }
}

// In llm_prompts.json
{
  "describe_image": {
    "system_template": "You are an AI that describes images accurately.",
    "user_template": "Describe this image. <img {url}>"
  },
  "generate_image_commentary": {
    "system_template": "{persona} Toxicity: {toxicity}",
    "user_template": "Post about: {image_description}. {topics_instruction}"
  }
}
```

### Key Features

- **Database Integration**: Queries images and topics
- **Vision LLM**: Uses llm_v for image description
- **Text LLM**: Uses standard LLM for commentary
- **Async Processing**: LLM calls are asynchronous
- **Topic Linking**: Automatically links article topics to post
- **Fallback**: Rule-based agents share without LLM

## Example: Search Action

The search action demonstrates topic-based content discovery with agent decision-making for engagement.

### Overview

The search action allows agents to:
1. Sample a topic from their interests (weighted by interaction count)
2. Query the database for up to 10 recent posts on that topic from other users
3. Randomly select one post from the results
4. Decide how to engage (comment, share, or react)
5. Execute the chosen action

This action is particularly useful for Explorer archetype agents who actively seek out content.

### Implementation Components

#### 1. Database Methods

```python
# In db_middleware.py

def search_posts_by_topic(self, topic_id: str, agent_id: str, limit: int = 10) -> List[str]:
    """
    Search for recent posts on a specific topic from other users.
    
    Args:
        topic_id: Topic/interest UUID to search for
        agent_id: Agent UUID (to exclude agent's own posts)
        limit: Maximum number of posts to return (default: 10)
        
    Returns:
        List[str]: List of post UUIDs from other users on this topic
    """
    from YSimulator.YServer.classes.models import PostTopic, Post, Round
    
    session = Session(self.engine)
    try:
        # Query posts with this topic, excluding agent's own posts, ordered by recency
        posts = (
            session.query(Post.id)
            .join(PostTopic, Post.id == PostTopic.post_id)
            .join(Round, Post.round == Round.id)
            .filter(PostTopic.topic_id == topic_id)
            .filter(Post.user_id != agent_id)
            .order_by(Round.day.desc(), Round.hour.desc())
            .limit(limit)
            .all()
        )
        return [post.id for post in posts]
    finally:
        session.close()

def get_topic_id_by_name(self, topic_name: str) -> Optional[str]:
    """Get topic/interest ID by name."""
    from YSimulator.YServer.classes.models import Interest
    
    session = Session(self.engine)
    try:
        interest = session.query(Interest).filter(
            Interest.interest == topic_name
        ).first()
        return interest.iid if interest else None
    finally:
        session.close()
```

#### 2. LLM Service Method

```python
# In llm_service.py

def decide_search_action(self, cluster_id: int, post_content: str, agent_attrs: dict = None) -> str:
    """
    Decide which action to perform on a searched post.
    
    LLM agents use this to decide how to engage with discovered content.
    
    Returns one of: "COMMENT", "SHARE", "LIKE", "LOVE", "LAUGH", "ANGRY", "SAD", "IGNORE"
    """
    persona = self._build_persona(cluster_id, agent_attrs)
    
    # Get prompt templates from configuration
    search_action_config = self.prompts_config.get("decide_search_action", {})
    system_template = search_action_config.get("system_template")
    user_template = search_action_config.get("user_template")
    
    # Format and call LLM
    system_msg = system_template.format(persona=persona)
    user_msg = user_template.format(post_content=post_content)
    
    result = self._call_llm(system_msg, user_msg).strip().upper()
    
    # Parse response for valid actions
    if "COMMENT" in result: return "COMMENT"
    if "SHARE" in result: return "SHARE"
    # ... other reactions ...
    
    return DEFAULT_FALLBACK_REACTION
```

#### 3. Client Action Handler

```python
# In client.py

def _handle_search_action(self, agent, agent_type, pending_llm_reactions, actions):
    """Handle search action for an agent."""
    # Log action initiation
    self.logger.info(
        f"search action initiated: agent={agent.username}, type={agent_type}",
        extra={"extra_data": {"agent_id": agent.id, "agent_type": agent_type}}
    )
    
    # 1. Sample topic from agent's interests
    agent_attrs = self._extract_agent_attrs(agent)
    selected_topic = agent_attrs.get("topic")
    
    if not selected_topic:
        self.logger.debug(f"search action skipped: no topics for agent {agent.username}")
        return
    
    # 2. Get topic ID
    topic_id = ray.get(self.server.get_topic_id_by_name.remote(selected_topic))
    if not topic_id:
        return
    
    # 3. Search for posts
    found_posts = ray.get(self.server.search_posts_by_topic.remote(
        topic_id, agent.id, limit=10
    ))
    
    if not found_posts:
        self.logger.debug(f"search action: no posts found for topic '{selected_topic}'")
        return
    
    # 4. Randomly select one post
    target_post = random.choice(found_posts)
    post_data = ray.get(self.server.get_post.remote(target_post))
    post_content = post_data.get("tweet", "")
    
    # 5. Decide engagement
    if agent_type == "llm":
        # LLM decides action asynchronously
        future = generate_llm_search_action_async(
            self.llm, agent.cluster, post_content, agent_attrs
        )
        pending_llm_reactions.append((agent.id, agent.cluster, target_post, future))
    else:
        # Rule-based: random selection
        selected_action = random.choice(["comment", "share", "react"])
        
        if selected_action == "comment":
            action = generate_rule_based_comment(agent.id, agent.cluster, target_post)
        elif selected_action == "share":
            action = generate_rule_based_share(agent.id, agent.cluster, target_post)
        else:
            reaction_type = random.choice(BASIC_REACTIONS)
            action = ActionDTO(agent.id, agent.cluster, reaction_type, target_post_id=target_post)
        
        actions.append(action)
```

#### 4. Integration with Simulation Loop

```python
# In client.py _simulate() method

# In action selection
action_type, agent_type, target = self.__select_action(agent, recent_posts)

if action_type == "search":
    self._handle_search_action(agent, agent_type, pending_llm_reactions, actions)
```

### Configuration

```json
// In simulation_config.json
{
  "agents": {
    "actions_likelihood": {
      "post": 0.3,
      "read": 0.2,
      "search": 0.15,  // Weight for search action
      "follow": 0.1
    }
  },
  "agent_archetypes": {
    "enabled": true,
    "agent_downcast": true,  // Force validators and explorers to use rule-based behavior
    "distribution": {
      "explorer": 0.33,
      "validator": 0.33,
      "broadcaster": 0.34
    }
  }
}

// In llm_prompts.json
{
  "decide_search_action": {
    "system_template": "{persona} You searched for posts on a topic you're interested in and found relevant content. Decide how to engage with it.",
    "user_template": "You found this post on your topic of interest:\n\n\"{post_content}\"\n\nHow do you want to engage? Reply with ONLY ONE WORD from these options:\n- COMMENT (engage in discussion, share your thoughts)\n- SHARE (reshare with your followers)\n- LIKE (positive, agree)\n- LOVE (strongly positive)\n- LAUGH (funny, humorous)\n- ANGRY (negative, disagree)\n- SAD (disappointing, concerning)\n- IGNORE (not interested, skip)\n\nYour choice:",
    "note": "Used when agents perform search action to decide engagement with discovered posts"
  }
}
```

### Logging

The search action includes comprehensive logging for debugging and analysis:

```python
# Action initiation
self.logger.info(
    f"search action initiated: agent={agent.username}, type={agent_type}",
    extra={"extra_data": {"agent_id": agent.id, "agent_type": agent_type, "archetype": agent.archetype}}
)

# Topic sampling
self.logger.info(
    f"search action: topic sampled '{selected_topic}' for agent {agent.username}",
    extra={"extra_data": {"agent_id": agent.id, "topic": selected_topic}}
)

# Search results
self.logger.info(
    f"search action: found {len(found_posts)} posts on topic '{selected_topic}'",
    extra={"extra_data": {"agent_id": agent.id, "topic": selected_topic, "posts_found": len(found_posts)}}
)

# Post selection
self.logger.info(
    f"search action: selected post {target_post} on topic '{selected_topic}'",
    extra={"extra_data": {"agent_id": agent.id, "topic": selected_topic, "target_post_id": target_post}}
)

# Rule-based action decision
self.logger.info(
    f"search action: rule-based agent selected '{selected_action}' action",
    extra={"extra_data": {"agent_id": agent.id, "selected_action": selected_action}}
)
```

### Key Features

- **Topic-based Discovery**: Uses agent interests for content discovery
- **Weighted Sampling**: Topics sampled by interaction frequency
- **Database Queries**: Efficient SQL joins with Round for chronological ordering
- **Async LLM Processing**: Parallel decision-making using Ray
- **Rule-based Fallback**: Simple random selection for non-LLM agents
- **Comprehensive Logging**: Detailed logging at each step for analysis
- **Archetype Alignment**: Explorer archetype focuses on search action

### Testing Search Action

```python
# Test database query
def test_search_posts_by_topic():
    db = DatabaseMiddleware(...)
    
    # Create test posts with topics
    topic_id = db.add_or_get_interest("Technology")
    post_id = db.add_post({"user_id": "user1", "tweet": "Test", "round": round_id})
    db.add_post_topic(post_id, topic_id)
    
    # Search from different user
    results = db.search_posts_by_topic(topic_id, "user2", limit=10)
    assert len(results) > 0
    assert post_id in results

# Test action flow
def test_search_action_flow():
    # Setup agent with interests
    agent = AgentProfile(
        id="agent1",
        interests=[["Technology", "Sports"], [5, 2]]
    )
    
    # Execute search action
    actions = []
    pending_reactions = []
    _handle_search_action(agent, "rule_based", pending_reactions, actions)
    
    # Verify action created
    assert len(actions) > 0
    assert actions[0].action_type in ["COMMENT", "SHARE", "LIKE", "ANGRY"]
```

## Conclusion

Adding new actions to YSimulator follows a consistent pattern:
1. Define the data model
2. Implement storage in middleware OR repository layer (recommended)
3. Add server handler
4. Implement client logic
5. Test thoroughly

**Recommended Approach**: Use the Repository/Service pattern for new extensions to benefit from:
- Better testability with mocked repositories
- Clearer separation of concerns
- Easier maintenance and refactoring
- Support for multiple storage backends

**Legacy Approach**: DatabaseMiddleware is still fully supported for backward compatibility.

Follow the patterns established in existing actions (posts, interactions) and refer to this guide when adding new capabilities.

For detailed Repository Pattern documentation, see [REPOSITORY_PATTERN.md](../architecture/REPOSITORY_PATTERN.md).

For questions or improvements to this guide, please open an issue on GitHub.

## Related Documentation

- **[Configuration Guide](../configuration/CONFIG.md)** - Configure simulation parameters and agent behaviors
- **[Architecture Overview](../architecture/ARCHITECTURE.md)** - Understand the system architecture (updated with new layers)
- **[Repository Pattern Guide](../architecture/REPOSITORY_PATTERN.md)** - NEW: Detailed documentation on the repository pattern
- **[Codebase Analysis](CODEBASE_ANALYSIS.md)** - Complete codebase overview (updated)
- **[Opinion Dynamics](../features/OPINION_DYNAMICS.md)** - Add opinion-based behaviors to new actions
- **[Action Logging](../logging/ACTION_LOGGING.md)** - Ensure new actions are properly logged
