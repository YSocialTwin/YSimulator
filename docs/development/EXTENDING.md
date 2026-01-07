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

### Client Architecture (Updated - Post Phase 1 Refactoring)
```
SimulationClient (Ray Actor)
├── run() - Main simulation loop
├── _execute_slot() - Execute one time slot
├── _dispatch_action_with_generator() - ✅ NEW: Unified action dispatch
├── action_generators/ - ✅ NEW: Modular action generation framework
│   ├── factory.py - Generator routing (10 action types)
│   ├── base_generator.py - Abstract base with opinion dynamics
│   ├── post_generator.py - POST action generation
│   ├── comment_generator.py - COMMENT with opinion dynamics
│   ├── read_generator.py - READ with reactions
│   ├── follow_generator.py - FOLLOW decisions
│   ├── share_generator.py - SHARE with LLM commentary
│   ├── share_link_generator.py - SHARE_LINK with topic extraction
│   ├── search_generator.py - SEARCH with reactions
│   ├── image_generator.py - IMAGE posts
│   ├── cast_generator.py - CAST actions
│   └── reply_generator.py - ✅ REPLY-TO-MENTION (refactored)
├── actions/ - Action implementation modules
│   ├── llm_actions.py - LLM-powered action generation
│   └── rule_based_actions.py - Rule-based action generation
├── agent_manager.py - Agent lifecycle management
├── activity_selector.py - Action type selection
└── churn_manager.py - Population dynamics
```

### Server Architecture (Updated)
```
OrchestratorServer (Ray Actor)
├── Coordination Methods
│   ├── get_instruction() - Provide time coordination
│   ├── register_client() - Client registration
│   └── heartbeat() - Client liveness tracking
├── Action Handlers
│   ├── submit_action() - Receive and process actions
│   └── submit_actions_batch() - Batch processing
├── Data Access Layer
│   └── Repository/Service Pattern - Modern architecture (100% complete)
│       ├── services/ - Business logic
│       │   ├── user_service.py
│       │   ├── post_service.py
│       │   └── recommendation_service.py
│       └── repositories/ - Data access
│           ├── sql_repository.py
│           └── redis_repository.py
└── interests_modeling/ - Interest tracking
    └── interest_manager.py
```

### Action Flow (Modern Architecture - Post Phase 1)
```
Client Agent → ActionGeneratorFactory → Generator → submit_action() → Server
                                                         ↓
                                            DatabaseServiceAdapter
                                                         ↓
                                              Service Layer
                                                         ↓
                                             Repository Layer
                                                         ↓
                                             Database (SQL + Redis)
```

## Using the Repository Pattern

YSimulator uses the **Repository Pattern** for complete separation of concerns and testability. This is the standard approach for all code.

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

### Adding Actions with the Service Layer

All new actions should use the Repository/Service pattern. Here's the complete flow:

**1. Define Data Model** (`classes/models.py`):
```python
from sqlalchemy import Column, String, Text, Integer, ForeignKey

class Share(Base):
    """Model for share actions."""
    __tablename__ = "shares"
    
    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(Integer, ForeignKey("user_mgmt.id"), nullable=False)
    post_id = Column(String(36), ForeignKey("posts.id"), nullable=False)
    share_comment = Column(Text, nullable=True)
    day = Column(Integer, nullable=False)
    slot = Column(Integer, nullable=False)
```

**2. Add Repository Method** (`repositories/sql_repository.py`):
```python
def add_share(self, share_data: Dict[str, Any]) -> Optional[str]:
    """Store share in database."""
    session = Session(self.engine)
    try:
        share = Share(**share_data)
        session.add(share)
        session.commit()
        return share_data["id"]
    except Exception as e:
        session.rollback()
        self.logger.error(f"Failed to add share: {e}")
        return None
    finally:
        session.close()
```

**3. Add Service Method** (`services/post_service.py`):
```python
def add_share(self, share_data: Dict[str, Any]) -> Optional[str]:
    """Add a share action."""
    share_id = str(uuid.uuid4())
    share_data["id"] = share_id
    return self.post_repo.add_share(share_data)
```

**4. Update Server** (`YServer/server.py`):
```python
@ray.method(num_returns=1)
@log_server_request
def submit_share(self, user_id: str, post_id: str, comment: str = None):
    """Handle share action submission."""
    share_data = {
        "user_id": user_id,
        "post_id": post_id,
        "comment": comment,
        "day": self.day,
        "slot": self.slot,
    }
    share_id = self.db.add_share(share_data)  # Uses DatabaseServiceAdapter
    return {"success": share_id is not None, "share_id": share_id}
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

    if agent_type == "llm":
        # LLM: Fire off async call for intelligent share decision
        agent_attrs = self._extract_agent_attrs(agent)
        post_to_share = self._select_post_to_share(agent)
        
        if post_to_share:
            future = generate_llm_share_async(
                self.llm, 
                agent.cluster, 
                post_to_share["content"],
                agent_attrs
            )
            pending_llm_shares.append((agent.id, agent.cluster, post_to_share["id"], future))
    else:
        # Rule-based: Immediate decision
        post_to_share = self._select_post_to_share(agent)
        if post_to_share:
            share_comment = generate_rule_based_share(
                agent.cluster, 
                post_to_share["content"]
            )
            actions.append(ActionDTO(
                agent_id=agent.id,
                cluster_id=agent.cluster,
                action_type="SHARE",
                content=share_comment,
                target_post_id=post_to_share["id"]
            ))
```

#### Option B: Add Action Generation Functions

**For LLM-based actions**, add to `YClient/actions/llm_actions.py`:

```python
def generate_llm_share_async(
    llm_handle: Any,
    cluster_id: int,
    post_content: str,
    agent_attrs: Optional[Dict[str, Any]] = None,
) -> ray.ObjectRef:
    """
    Initiate async LLM share comment generation.

    Args:
        llm_handle: Ray actor handle for the LLM service
        cluster_id: Cluster/group the agent belongs to
        post_content: Content of the post being shared
        agent_attrs: Optional dict with agent attributes

    Returns:
        Ray ObjectRef: Future that will resolve to share comment (str)
    """
    return llm_handle.generate_share_comment.remote(
        cluster_id, post_content, agent_attrs
    )
```

**For rule-based actions**, add to `YClient/actions/rule_based_actions.py`:

```python
def generate_rule_based_share(cluster_id: int, post_content: str) -> str:
    """
    Generate a simple rule-based share comment.

    Args:
        cluster_id: Cluster/group the agent belongs to
        post_content: Content of the post being shared

    Returns:
        Share comment text (str)
    """
    templates = [
        "Check this out!",
        "Interesting perspective",
        "Worth reading",
        "Sharing this",
    ]
    return random.choice(templates)
```

#### Option C: Integrate into Activity Selector

If your action needs custom selection logic, update `YClient/activity_selector.py`:

```python
def select_action_for_agent(
    agent: AgentProfile,
    config: dict,
    current_day: int,
    current_slot: int
) -> str:
    """
    Select an action type for an agent based on configuration and context.
    
    Args:
        agent: Agent profile
        config: Simulation configuration
        current_day: Current simulation day
        current_slot: Current time slot
        
    Returns:
        Action type: "POST", "READ", "COMMENT", "SHARE", "FOLLOW", "SEARCH"
    """
    # Get action probabilities from config
    action_probs = config.get("action_likelihoods", {})
    
    # Apply archetype-specific adjustments
    if agent.archetype == "broadcaster":
        action_probs["POST"] *= 2.0  # Broadcasters post more
        action_probs["SHARE"] *= 1.5  # And share more
    elif agent.archetype == "validator":
        action_probs["COMMENT"] *= 2.0  # Validators comment more
        action_probs["SHARE"] *= 0.5  # But share less
    
    # Normalize and select
    total = sum(action_probs.values())
    normalized = {k: v/total for k, v in action_probs.items()}
    
    return random.choices(
        list(normalized.keys()),
        weights=list(normalized.values())
    )[0]
```

### Step 6: Integrate into Main Execution Loop

The client now uses a modular action execution system. Integrate your new action:

#### In `YClient/client.py` - Main execution loop:

```python
def _execute_slot(self, day: int, slot: int):
    """Execute one time slot of the simulation."""
    actions = []
    pending_llm_posts = []
    pending_llm_reads = []
    pending_llm_shares = []  # Add for your new action
    
    # Phase 1: Select actions for each agent
    for agent in self.agents:
        # Determine if agent is active this slot
        if not self._is_agent_active(agent, slot):
            continue
        
        # Select action type using activity selector
        action_type = select_action_for_agent(
            agent, self.simulation_config, day, slot
        )
        
        # Determine agent type (LLM or rule-based)
        agent_type = "llm" if agent.llm else "rule"
        
        # Route to appropriate handler
        if action_type == "POST":
            self._handle_post_action(agent, agent_type, day, slot, pending_llm_posts, actions)
        elif action_type == "READ":
            self._handle_read_action(agent, agent_type, day, slot, pending_llm_reads, actions)
        elif action_type == "SHARE":
            self._handle_share_action(agent, agent_type, day, slot, pending_llm_shares, actions)
        # ... other action types ...
    
    # Phase 2: Gather LLM results (scatter-gather pattern)
    if pending_llm_posts:
        post_contents = ray.get([f[2] for f in pending_llm_posts])
        for i, content in enumerate(post_contents):
            agent_id, cluster_id, _ = pending_llm_posts[i]
            actions.append(ActionDTO(agent_id, cluster_id, "POST", content=content))
    
    if pending_llm_shares:
        share_comments = ray.get([f[3] for f in pending_llm_shares])
        for i, comment in enumerate(share_comments):
            agent_id, cluster_id, post_id, _ = pending_llm_shares[i]
            actions.append(ActionDTO(
                agent_id, cluster_id, "SHARE", 
                content=comment, target_post_id=post_id
            ))
    
    # Phase 3: Submit all actions to server
    if actions:
        self._submit_actions_batch(actions, day, slot)
```

#### Key Integration Points:

1. **ActionExecutorMixin**: Your handler method (`_handle_share_action`)
2. **Action modules**: Your generation functions (LLM and rule-based)
3. **Activity selector**: Update action probabilities/logic if needed
4. **Main loop**: Add routing to your handler in `_execute_slot()`

#### Example: Complete Share Action Integration (Updated - January 2026)

**Note**: As of January 2026, action handlers have been refactored into dedicated generator classes. Below shows the new pattern:

```python
# 1. In action_generators/share_generator.py (NEW)
class ShareGenerator(BaseActionGenerator):
    """Handles SHARE actions with LLM commentary support."""
    
    def generate(self, agent, target, agent_type):
        """Generate share action for an agent."""
        # Get recommended posts
        posts = self.server.get_recommended_posts.remote(
            self.context.client_id, agent.id
        ).get()
        
        if not posts:
            return [], [], {}
        
        # Select post to share (first one for simplicity)
        post_to_share = posts[0]
        
        if agent_type == "llm":
            # Async LLM call for personalized commentary
            agent_attrs = self._extract_agent_attrs(agent)
            future = generate_llm_share_async(
                self.context.llm, agent.cluster, 
                post_to_share["content"], agent_attrs,
                post_to_share["author_name"]
            )
            pending_calls = [(
                agent.id, agent.cluster, post_to_share["id"], future, "SHARE"
            )]
            return [], pending_calls, {}
        else:
            # Rule-based: immediate reshare
            immediate_actions = [ActionDTO(
                agent_id=agent.id,
                cluster_id=agent.cluster,
                action_type="SHARE",
                content=post_to_share["content"],  # No commentary
                target_post_id=post_to_share["id"]
            )]
            return immediate_actions, [], {}

# 2. In actions/llm_actions.py
def generate_llm_share_async(llm_handle, cluster_id, content, attrs, author_name):
    """Generate LLM share commentary asynchronously."""
    return llm_handle.generate_share_commentary.remote(
        cluster_id, content, attrs, author_name
    )

# 3. In LLM_interactions/llm_service.py
def generate_share_commentary(self, cluster_id, post_content, agent_attrs, author_name):
    """Generate personalized share commentary using LLM."""
    # Build persona from agent attributes
    persona = self._build_persona(agent_attrs)
    
    # Get prompt from prompts.json
    system_prompt = self.prompts_config["generate_share_commentary"]["system_template"]
    user_prompt = self.prompts_config["generate_share_commentary"]["user_template"]
    
    # Fill in placeholders
    system_text = system_prompt.format(
        persona=persona, 
        toxicity=self._get_toxicity_instruction(agent_attrs)
    )
    user_text = user_prompt.format(
        author_name=author_name,
        post_content=post_content
    )
    
    # Call LLM
    commentary = self.llm_client.generate(system_text, user_text, max_tokens=50)
    return commentary[:200]  # Max 200 chars

# 4. In action_generators/factory.py
class ActionGeneratorFactory:
    """Routes action types to appropriate generators."""
    
    def get_generator(self, action_type: str) -> BaseActionGenerator:
        generators = {
            "share": ShareGenerator,
            "post": PostGenerator,
            "comment": CommentGenerator,
            # ... other generators
        }
        generator_class = generators.get(action_type.lower())
        if not generator_class:
            raise ValueError(f"No generator for action type: {action_type}")
        return generator_class(self.context)  
def generate_rule_based_share(cluster_id, content):
    """Generate simple share comment."""
    return random.choice(["Check this out!", "Interesting!", "Worth reading"])

# 4. In client.py - main loop
def _execute_slot(self, day, slot):
    actions = []
    pending_llm_shares = []
    
    for agent in self.agents:
        action_type = self._select_action_type(agent)
        agent_type = "llm" if agent.llm else "rule"
        
        if action_type == "SHARE":
            self._handle_share_action(
                agent, agent_type, day, slot, pending_llm_shares, actions
            )
    
    # Gather LLM results
    if pending_llm_shares:
        comments = ray.get([f[3] for f in pending_llm_shares])
        for i, comment in enumerate(comments):
            agent_id, cluster_id, post_id, _ = pending_llm_shares[i]
            actions.append(ActionDTO(
                agent_id, cluster_id, "SHARE", 
                content=comment, target_post_id=post_id
            ))
    
    # Submit batch
    self._submit_actions_batch(actions, day, slot)
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

### 2. Middleware (services and repositories)
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
    share_id = self.db.add_share(user_id, post_id, self.current_day)
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

### 1. Unit Tests for Action Functions

Test your action generation functions in isolation:

```python
# tests/test_actions.py
import pytest
from YSimulator.YClient.actions.rule_based_actions import generate_rule_based_share
from YSimulator.YClient.actions.llm_actions import generate_llm_share_async
import ray

def test_rule_based_share():
    """Test rule-based share comment generation."""
    comment = generate_rule_based_share(cluster_id=1, post_content="Test post")
    assert isinstance(comment, str)
    assert len(comment) > 0

@pytest.mark.asyncio
async def test_llm_share_async():
    """Test LLM share comment generation."""
    # Mock LLM handle
    @ray.remote
    class MockLLMService:
        def generate_share_comment(self, cluster_id, content, attrs):
            return "Interesting perspective on this topic!"
    
    llm_handle = MockLLMService.remote()
    future = generate_llm_share_async(
        llm_handle, 
        cluster_id=1, 
        content="Test post",
        attrs={"name": "TestAgent"}
    )
    
    result = ray.get(future)
    assert isinstance(result, str)
    assert len(result) > 0
```

### 2. Integration Tests with Repository/Service Pattern

Test the full data flow with mocked dependencies:

```python
# tests/test_share_service.py
import pytest
from unittest.mock import Mock, MagicMock
from YSimulator.YServer.services import PostService
from YSimulator.YServer.repositories import SQLPostRepository

def test_share_action_service():
    """Test share action through service layer."""
    # Mock repository
    mock_repo = Mock(spec=SQLPostRepository)
    mock_repo.add_share.return_value = "share-uuid-123"
    
    # Create service with mock
    post_service = PostService(mock_repo)
    
    # Test share creation
    share_id = post_service.create_share({
        "user_id": "user-1",
        "post_id": "post-123",
        "comment": "Great post!",
        "day": 5,
        "slot": 10
    })
    
    # Verify
    assert share_id == "share-uuid-123"
    mock_repo.add_share.assert_called_once()
```

### 3. Client-Server Integration Tests

Test the complete flow through Ray actors:

```python
# tests/test_client_server_integration.py
import pytest
import ray
from YSimulator.YServer.server import OrchestratorServer
from YSimulator.YClient.client import SimulationClient

@pytest.fixture
def setup_ray():
    """Initialize Ray for testing."""
    if not ray.is_initialized():
        ray.init(ignore_reinit_error=True)
    yield
    ray.shutdown()

def test_share_action_flow(setup_ray):
    """Test complete share action flow from client to server."""
    # Create server
    server_config = {
        "database_type": "sqlite",
        "database_path": ":memory:",
        "use_redis": False
    }
    server = OrchestratorServer.remote(server_config)
    
    # Create client with mock LLM
    @ray.remote
    class MockLLM:
        def generate_share_comment(self, cluster_id, content, attrs):
            return "Test share comment"
    
    llm = MockLLM.remote()
    client_config = {
        "action_likelihoods": {"SHARE": 1.0},
        "recsys_type": "random"
    }
    agent_config = {
        "agents": [{
            "id": "agent-1",
            "username": "test_agent",
            "llm": False,
            "archetype": "broadcaster"
        }]
    }
    
    client = SimulationClient.remote(
        "client-1", llm, agent_config, client_config
    )
    
    # Register and execute
    ray.get(server.register_client.remote("client-1", 1))
    ray.get(client.register_agents.remote(server))
    
    # Execute slot (will generate share action)
    ray.get(client._execute_slot.remote(0, 0))
    
    # Verify action was submitted (check server logs or database)
    # This is a simplified example - real test would verify database state
```

### 4. End-to-End Testing

Test with actual configuration files:

```bash
# Create test configuration
mkdir -p test_config
cp example/rule_population_100/server_config.json test_config/
cp example/rule_population_100/simulation_config.json test_config/

# Modify simulation_config.json to add SHARE action
# "action_likelihoods": {"SHARE": 5.0, "POST": 3.0, ...}

# Run simulation
python run_server.py --config test_config &
sleep 5  # Wait for server to start
python run_client.py --config test_config

# Check logs for share actions
grep "SHARE" test_config/logs/*.log
```

### 5. Database Testing

Test database schema and migrations:

```python
# tests/test_database.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from YSimulator.YServer.classes.models import Base, ShareModel

def test_share_model_creation():
    """Test ShareModel can be created and saved."""
    # In-memory SQLite for testing
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Create share
    share = ShareModel(
        id="test-share-uuid",
        user_id="user-1",
        post_id="post-123",
        share_comment="Test comment",
        day=5,
        slot=10,
        timestamp=1234567890
    )
    
    session.add(share)
    session.commit()
    
    # Retrieve and verify
    retrieved = session.query(ShareModel).filter_by(
        id="test-share-uuid"
    ).first()
    
    assert retrieved is not None
    assert retrieved.user_id == "user-1"
    assert retrieved.post_id == "post-123"
    assert retrieved.share_comment == "Test comment"
    
    session.close()
```

### 6. Running Tests

```bash
# Run all tests
pytest YSimulator/tests/

# Run specific test file
pytest YSimulator/tests/test_actions.py

# Run with coverage
pytest --cov=YSimulator --cov-report=html YSimulator/tests/

# Run specific test function
pytest YSimulator/tests/test_actions.py::test_rule_based_share -v
```
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

## Common Pitfalls and Modern Solutions

### 1. Not Using the Scatter-Gather Pattern for LLM Calls

```python
# BAD - Sequential LLM calls (slow)
for agent in agents:
    if agent.llm:
        content = ray.get(llm.generate_post.remote(agent.cluster))
        actions.append(ActionDTO(agent.id, agent.cluster, "POST", content=content))

# GOOD - Parallel LLM calls (fast)
# Scatter phase - fire off all LLM calls
futures = []
for agent in agents:
    if agent.llm:
        future = generate_llm_post_async(llm, agent.cluster, day, slot)
        futures.append((agent.id, agent.cluster, future))

# Gather phase - wait for all at once
contents = ray.get([f[2] for f in futures])
for i, content in enumerate(contents):
    agent_id, cluster_id, _ = futures[i]
    actions.append(ActionDTO(agent_id, cluster_id, "POST", content=content))
```

### 2. Mixing LLM and Rule-Based Logic

```python
# BAD - Intermixing different agent types
def handle_action(agent):
    if agent.llm:
        # Complex LLM logic
        content = generate_with_llm(agent)
    else:
        # Simple rule logic
        content = generate_with_rules(agent)
    return content

# GOOD - Separate handler methods
def _handle_action_llm(self, agent, pending_futures):
    """Handler for LLM-based agents."""
    future = generate_llm_action_async(self.llm, agent.cluster)
    pending_futures.append((agent.id, agent.cluster, future))

def _handle_action_rule(self, agent, actions):
    """Handler for rule-based agents."""
    content = generate_rule_based_action(agent.cluster)
    actions.append(ActionDTO(agent.id, agent.cluster, "ACTION", content=content))
```

### 3. Forgetting Temporal Context

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

### 4. Not Using UUIDs for Distributed Systems

```python
# BAD - auto-increment can conflict in distributed systems
id = db.Column(db.Integer, primary_key=True, autoincrement=True)

# GOOD - UUID for distributed ID generation
id = db.Column(db.String(36), primary_key=True)
# Generate with: str(uuid.uuid4())
```

### 5. Ignoring Repository Pattern Benefits

```python
# BAD - Direct database access in business logic
def create_share(self, user_id, post_id):
    session = Session(self.engine)
    share = ShareModel(id=str(uuid.uuid4()), user_id=user_id, post_id=post_id)
    session.add(share)
    session.commit()
    session.close()
    # Hard to test, tightly coupled to database

# GOOD - Using repository pattern
def create_share(self, user_id, post_id):
    return self.share_repository.add_share({
        "user_id": user_id,
        "post_id": post_id
    })
    # Easy to test with mock repository, decoupled from storage
```

### 6. Not Handling Agent Archetypes

```python
# BAD - Treating all agents the same
action_type = random.choice(["POST", "READ", "COMMENT"])

# GOOD - Respecting archetype behaviors
if agent.archetype == "broadcaster":
    # Broadcasters post and share more
    action_probs = {"POST": 0.4, "SHARE": 0.3, "READ": 0.2, "COMMENT": 0.1}
elif agent.archetype == "validator":
    # Validators comment and engage more
    action_probs = {"COMMENT": 0.4, "READ": 0.3, "POST": 0.2, "SHARE": 0.1}
else:  # explorer
    # Explorers read and search more
    action_probs = {"READ": 0.4, "SEARCH": 0.3, "POST": 0.2, "COMMENT": 0.1}

action_type = random.choices(
    list(action_probs.keys()),
    weights=list(action_probs.values())
)[0]
```

### 7. Ignoring Redis Consolidation

```python
# BAD - Redis data is lost when sliding window expires
def add_share(self, data):
    if self.use_redis:
        self.redis_client.hset(f"share:{id}", data)
    # Missing: SQL storage and day indexing

# GOOD - Always persist to SQL + index for consolidation
def add_share(self, data):
    share_id = str(uuid.uuid4())
    
    if self.use_redis:
        self.redis_client.hset(f"share:{share_id}", mapping=data)
        self.redis_client.sadd(f"shares:day:{data['day']}", share_id)
    
    # Always store in SQL for durability
    share = ShareModel(id=share_id, **data)
    self.session.add(share)
    self.session.commit()
    
    return share_id
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
# In service layer

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
# In service layer

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
    db = DatabaseServiceAdapter(...)
    
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

YSimulator has evolved to support a modern, modular architecture for extending agent actions. The current system provides two approaches:

### Modern Approach (Recommended)

1. **Client Side**: Use Action Generator Framework (Updated January 2026 - Phase 1 Complete)
   - Create new generator class in `action_generators/` (e.g., `my_action_generator.py`)
   - Extend `BaseActionGenerator` abstract class
   - Implement `generate(agent, target, agent_type)` method
   - Add generator to `ActionGeneratorFactory` routing
   - Use opinion dynamics helpers from base class for consistency
   - Action automatically integrated via factory pattern
   - **Current Generators** (10 total): POST, COMMENT, READ, FOLLOW, SHARE, SHARE_LINK, SEARCH, IMAGE, CAST, REPLY
   - **Example**: See `reply_generator.py` for complete generator implementation with LLM/rule-based paths

2. **Server Side**: Use Repository/Service pattern
   - Define interface in `repositories/base_repository.py`
   - Implement SQL version in `repositories/sql_repository.py`
   - Implement Redis version in `repositories/redis_repository.py` (optional)
   - Create service in `services/` for business logic
   - Use service in server handler methods

3. **Benefits**:
   - ✅ Better testability with isolated generators and mocked dependencies
   - ✅ Clear separation of concerns (action generation vs execution)
   - ✅ Parallel LLM execution (10x faster for large populations)
   - ✅ Support for multiple storage backends
   - ✅ Easier to maintain and extend (single responsibility per generator)
   - ✅ Archetype-aware action selection
   - ✅ Opinion dynamics helpers shared across all generators

### Legacy Approach (Still Supported)

1. **Database Model**: Define in `classes/models.py`
2. **Middleware**: Add methods to `services and repositories`
3. **Server**: Add handler to `YServer/server.py`
4. **Client**: Implement action logic directly in `client.py`

**Note**: The legacy approach is fully functional and maintained for backward compatibility. New code should use the modern approach for better architecture.

### Key Architectural Improvements

- **Modular Actions**: Separate LLM and rule-based implementations
- **ActionExecutorMixin**: Centralized action handling
- **Scatter-Gather Pattern**: Parallel LLM calls for performance
- **Repository Pattern**: Abstracted data access
- **Agent Manager**: Dedicated agent lifecycle management
- **Activity Selector**: Intelligent action type selection
- **Churn Manager**: Dynamic population management

### Development Workflow

1. **Design**: Plan your action and data requirements
2. **Implement**: Follow the step-by-step guide above
3. **Test**: Write unit, integration, and end-to-end tests
4. **Document**: Update configuration and documentation
5. **Deploy**: Test in example configurations

### Getting Help

- **Architecture Questions**: See [Architecture Overview](../architecture/ARCHITECTURE.md)
- **Repository Pattern**: See [Repository Pattern Guide](../architecture/REPOSITORY_PATTERN.md)
- **Code Examples**: Check existing actions in `YClient/actions/`
- **Testing**: See test examples in `YSimulator/tests/`

## Related Documentation

- **[Configuration Guide](../configuration/CONFIG.md)** - Configure simulation parameters and agent behaviors
- **[Architecture Overview](../architecture/ARCHITECTURE.md)** - Understand the layered system architecture
- **[Repository Pattern Guide](../architecture/REPOSITORY_PATTERN.md)** - Detailed data access pattern documentation
- **[Agent Actions](../agents/AGENT_ACTIONS.md)** - Complete reference of all agent actions
- **[Agent Types](../agents/AGENT_TYPES.md)** - Understanding agent archetypes and behaviors
- **[Codebase Analysis](CODEBASE_ANALYSIS.md)** - Complete codebase overview with statistics
- **[Opinion Dynamics](../features/OPINION_DYNAMICS.md)** - Add opinion-based behaviors to actions
- **[Action Logging](../logging/ACTION_LOGGING.md)** - Ensure new actions are properly logged
- **[Code Formatting](FORMATTING.md)** - Follow project code standards

---

**Last Updated**: January 2026  
**Version**: 2.1 (Updated for modular architecture)  
**Contributors**: YSimulator Development Team

For questions or improvements to this guide, please open an issue on GitHub.
