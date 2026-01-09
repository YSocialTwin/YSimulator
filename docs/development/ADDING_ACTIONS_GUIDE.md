# Adding New Action Types to YSimulator

**Last Updated**: January 8, 2026  
**Architecture**: Phase 1-6 Complete  
**Estimated Time**: 1-2 hours

---

## 📚 Quick Navigation

- **[← Documentation Index](../getting-started/INDEX.md)** - Complete documentation
- **[Action Architecture](../architecture/ACTION_PROCESSOR_FRAMEWORK.md)** - Framework details
- **[Agent Actions Reference](../agents/AGENT_ACTIONS.md)** - All available actions
- **[EXTENDING.md](EXTENDING.md)** - General extension guide

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Prerequisites](#prerequisites)
3. [Architecture Overview](#architecture-overview)
4. [Step-by-Step Implementation](#step-by-step-implementation)
5. [Complete Example: Quote Action](#complete-example-quote-action)
6. [LLM Integration](#llm-integration)
7. [Opinion Dynamics Integration](#opinion-dynamics-integration)
8. [Testing Strategy](#testing-strategy)
9. [Troubleshooting](#troubleshooting)

---

## Quick Start

**Goal**: Add a new action type to YSimulator in ~30 minutes.

**Steps**:
1. Create action generator class in `YClient/action_generators/`
2. Add generator to factory in `factory.py`
3. Update ActionContext if needed
4. Add action handler in server (if required)
5. Test the action

**Result**: A fully functional new action type integrated into the simulation framework.

---

## Prerequisites

### Understanding Phase 1 Architecture

YSimulator uses the **Action Generator Framework** (Phase 1) for all actions:

```
Agent Decision → ActionGeneratorFactory → Specific Generator → Server
```

**Key Components**:
- `ActionGeneratorFactory`: Routes action types to generators
- `BaseGenerator`: Abstract base class with common functionality
- Specific Generators: `PostGenerator`, `CommentGenerator`, etc.
- `ActionContext`: Provides dependencies (server, LLM, opinions, etc.)

### Required Knowledge

- Python 3.8+ and async/await patterns
- Ray framework basics (remote calls, ObjectRefs)
- YSimulator architecture (Phases 1-6)
- Action DTO structure

### Files You'll Modify

```
YSimulator/
├── YClient/
│   ├── action_generators/
│   │   ├── factory.py ← Add routing
│   │   ├── your_new_generator.py ← CREATE THIS
│   │   └── base_generator.py ← Reference this
│   └── client.py ← Usually no changes needed
└── YServer/
    └── orchestrator_server.py ← May need action handler
```

---

## Architecture Overview

### Action Generator Pattern (Phase 1)

All actions follow this pattern:

```python
class YourActionGenerator(BaseGenerator):
    """Generator for YOUR_ACTION action type."""
    
    async def generate_action(
        self,
        agent: dict,
        agent_type: str,
        action_data: Optional[dict] = None
    ) -> Tuple[List[ActionDTO], List[ObjectRef], dict]:
        """
        Generate the action.
        
        Returns:
            - immediate_actions: Actions to execute now
            - pending_llm_calls: LLM futures to await
            - metadata: Additional info for logging
        """
        # Implementation here
        pass
```

### ActionContext

All generators receive an `ActionContext` with dependencies:

```python
@dataclass
class ActionContext:
    server: ActorHandle                    # Server actor
    llm_manager: LLMManager                # Phase 3: LLM operations
    simulation_config: dict                # Configuration
    agent_profiles: dict                   # Agent personas
    client_id: str                         # Client identifier
    logger: logging.Logger                 # Logging
    
    # Opinion dynamics (Phase 4)
    is_opinion_dynamics_enabled_fn: Callable
    calculate_opinion_updates_fn: Callable
    get_opinions_for_post_fn: Callable
    infer_page_agent_opinion_fn: Callable
    map_opinion_to_group_fn: Callable
```

### Action Flow

```
1. Agent selects action type (e.g., "QUOTE")
2. ActionGeneratorFactory routes to QuoteGenerator
3. QuoteGenerator.generate_action() called
4. Generator uses LLMManager for content (if LLM agent)
5. Generator creates ActionDTO
6. Action submitted to server via context.server.submit_action()
7. Server processes and stores action
```

---

## Step-by-Step Implementation

### Step 1: Create Generator Class

Create `YClient/action_generators/quote_generator.py`:

```python
"""Quote action generator - repost with commentary."""

import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass
import ray
from ray.util import ActorHandle
from ray import ObjectRef

from .base_generator import BaseGenerator, ActionContext
from ..action_dto import ActionDTO


class QuoteGenerator(BaseGenerator):
    """
    Generates QUOTE actions (reposting with original commentary).
    
    Similar to SHARE but includes original post in quoted context.
    """
    
    def __init__(self, context: ActionContext):
        """Initialize quote generator with context."""
        super().__init__(context)
        self.logger = logging.getLogger(__name__)
    
    async def generate_action(
        self,
        agent: dict,
        agent_type: str,
        action_data: Optional[dict] = None
    ) -> Tuple[List[ActionDTO], List[ObjectRef], dict]:
        """
        Generate a QUOTE action.
        
        Args:
            agent: Agent dict with id, cluster_id, etc.
            agent_type: "llm" or "rule_based"
            action_data: Optional dict with:
                - target_post_id: Post to quote
                - target_post_content: Original post text
        
        Returns:
            Tuple of (immediate_actions, pending_llm_calls, metadata)
        """
        agent_id = agent["id"]
        cluster_id = agent["cluster_id"]
        
        # Validate action_data
        if not action_data or "target_post_id" not in action_data:
            self.logger.warning(
                f"QUOTE action requires target_post_id for agent {agent_id}"
            )
            return [], [], {"error": "missing_target_post"}
        
        target_post_id = action_data["target_post_id"]
        target_post_content = action_data.get("target_post_content", "")
        
        # Generate commentary based on agent type
        if agent_type == "llm":
            # LLM-based: intelligent commentary
            commentary_future = await self._generate_llm_quote_commentary(
                agent, target_post_content
            )
            
            metadata = {
                "action_type": "QUOTE",
                "target_post_id": target_post_id,
                "generation_method": "llm"
            }
            
            # Return pending LLM call
            return [], [commentary_future], metadata
            
        else:
            # Rule-based: simple commentary
            commentary = self._generate_rule_based_quote_commentary(
                agent_id, target_post_content
            )
            
            # Create action immediately
            action = ActionDTO(
                agent_id=agent_id,
                cluster_id=cluster_id,
                action_type="QUOTE",
                content=commentary,
                target_post_id=target_post_id
            )
            
            metadata = {
                "action_type": "QUOTE",
                "target_post_id": target_post_id,
                "generation_method": "rule_based"
            }
            
            return [action], [], metadata
    
    async def _generate_llm_quote_commentary(
        self,
        agent: dict,
        target_post_content: str
    ) -> ObjectRef:
        """Generate commentary using LLM."""
        agent_attrs = self._extract_agent_attributes(agent)
        
        # Use LLMManager (Phase 3)
        commentary_future = await self.context.llm_manager.generate_quote_commentary_async(
            llm_handle=self.context.llm_manager.llm_handle,
            cluster_id=agent["cluster_id"],
            agent_attrs=agent_attrs,
            target_post_content=target_post_content
        )
        
        return commentary_future
    
    def _generate_rule_based_quote_commentary(
        self,
        agent_id: str,
        target_post_content: str
    ) -> str:
        """Generate simple rule-based commentary."""
        # Simple templates
        templates = [
            f"This is interesting! {target_post_content[:100]}",
            f"Check this out: {target_post_content[:100]}",
            f"Worth sharing: {target_post_content[:100]}"
        ]
        
        # Deterministic selection based on agent_id
        idx = hash(agent_id) % len(templates)
        return templates[idx]
    
    def _extract_agent_attributes(self, agent: dict) -> dict:
        """Extract agent attributes for LLM persona."""
        cluster_id = agent["cluster_id"]
        profile = self.context.agent_profiles.get(cluster_id, {})
        
        return {
            "agent_id": agent["id"],
            "name": agent.get("name", f"Agent_{agent['id'][:8]}"),
            "persona": profile.get("description", "Social media user"),
            "interests": agent.get("interests", [])
        }
```

### Step 2: Add to ActionGeneratorFactory

Update `YClient/action_generators/factory.py`:

```python
from .quote_generator import QuoteGenerator  # Add import

class ActionGeneratorFactory:
    """Factory for creating action generators."""
    
    def __init__(self, context: ActionContext):
        self.context = context
        
        # Initialize all generators
        self.generators = {
            "POST": PostGenerator(context),
            "COMMENT": CommentGenerator(context),
            "READ": ReadGenerator(context),
            "FOLLOW": FollowGenerator(context),
            "SHARE": ShareGenerator(context),
            "SHARE_LINK": ShareLinkGenerator(context),
            "SEARCH": SearchGenerator(context),
            "IMAGE": ImageGenerator(context),
            "CAST": CastGenerator(context),
            "REPLY": ReplyGenerator(context),
            "QUOTE": QuoteGenerator(context),  # Add here
        }
    
    def get_generator(self, action_type: str) -> BaseGenerator:
        """Get generator for action type."""
        generator = self.generators.get(action_type)
        
        if generator is None:
            raise ValueError(f"Unknown action type: {action_type}")
        
        return generator
```

### Step 3: Add LLM Method (if using LLM)

Update `YClient/llm_utils/llm_manager.py`:

```python
async def generate_quote_commentary_async(
    self,
    llm_handle: ActorHandle,
    cluster_id: int,
    agent_attrs: dict,
    target_post_content: str
) -> ObjectRef:
    """
    Generate quote commentary using LLM.
    
    Args:
        llm_handle: LLM actor handle
        cluster_id: Agent's cluster (persona)
        agent_attrs: Agent attributes for context
        target_post_content: Original post being quoted
    
    Returns:
        ObjectRef resolving to commentary string
    """
    prompt = self._create_quote_prompt(
        cluster_id, agent_attrs, target_post_content
    )
    
    # Call LLM asynchronously
    future = llm_handle.generate.remote(
        prompt=prompt,
        max_tokens=150,
        temperature=0.8
    )
    
    return future

def _create_quote_prompt(
    self,
    cluster_id: int,
    agent_attrs: dict,
    target_post_content: str
) -> str:
    """Create prompt for quote commentary."""
    persona = agent_attrs.get("persona", "Social media user")
    interests = ", ".join(agent_attrs.get("interests", []))
    
    prompt = f"""You are {agent_attrs['name']}, a {persona}.
Your interests: {interests}

You are quoting this post:
"{target_post_content}"

Write a brief commentary (1-2 sentences) explaining why you're sharing this.
Be authentic to your persona and interests.

Commentary:"""
    
    return prompt
```

### Step 4: Add Server Handler (if needed)

Most actions use the generic `submit_action()` handler. Only add a custom handler if you need special server-side processing.

Update `YServer/orchestrator_server.py` (optional):

```python
def submit_action(self, action_dto: ActionDTO, client_id: str):
    """
    Submit an action to the server.
    
    Handles all action types including QUOTE.
    """
    try:
        action_type = action_dto.action_type
        
        if action_type == "QUOTE":
            # Special handling if needed
            return self._handle_quote_action(action_dto, client_id)
        else:
            # Generic handling
            return self._handle_generic_action(action_dto, client_id)
    
    except Exception as e:
        self.logger.error(f"Error submitting action: {e}")
        return {"success": False, "error": str(e)}

def _handle_quote_action(self, action_dto: ActionDTO, client_id: str):
    """Handle QUOTE action specifically."""
    # Store quote post in database
    post_service = self.service_adapter.get_post_service()
    
    result = post_service.create_post(
        user_id=action_dto.agent_id,
        content=action_dto.content,
        quoted_post_id=action_dto.target_post_id,  # Link to original
        timestamp=datetime.now()
    )
    
    return {"success": True, "post_id": result["post_id"]}
```

### Step 5: Update Activity Selector (if needed)

If your action needs to be selectable by agents, add it to the archetype configuration.

Update `YClient/activity_selector.py` or configuration:

```python
# In archetype definitions
archetype_actions = {
    "casual_user": {
        "POST": 0.15,
        "READ": 0.50,
        "COMMENT": 0.10,
        "FOLLOW": 0.05,
        "SHARE": 0.10,
        "QUOTE": 0.10,  # Add here
    },
    # ... other archetypes
}
```

### Step 6: Add Configuration

Update simulation config to enable the action:

```yaml
# config/simulation_config.yaml
actions:
  enabled_types:
    - POST
    - COMMENT
    - READ
    - FOLLOW
    - SHARE
    - QUOTE  # Add here
  
  quote:
    max_length: 280  # Max commentary length
    require_target: true  # Must have target post
```

### Step 7: Test the Action

Create test file `tests/test_quote_generator.py`:

```python
import pytest
from YClient.action_generators.quote_generator import QuoteGenerator
from YClient.action_generators.base_generator import ActionContext

class TestQuoteGenerator:
    
    @pytest.fixture
    def context(self, mock_server, mock_llm_manager):
        """Create action context for testing."""
        return ActionContext(
            server=mock_server,
            llm_manager=mock_llm_manager,
            simulation_config={},
            agent_profiles={1: {"description": "Tech enthusiast"}},
            client_id="test_client",
            logger=logging.getLogger("test")
        )
    
    @pytest.fixture
    def generator(self, context):
        """Create quote generator."""
        return QuoteGenerator(context)
    
    @pytest.mark.asyncio
    async def test_generate_rule_based_quote(self, generator):
        """Test rule-based quote generation."""
        agent = {
            "id": "agent_001",
            "cluster_id": 1,
            "name": "TestUser"
        }
        
        action_data = {
            "target_post_id": "post_123",
            "target_post_content": "AI is transforming healthcare!"
        }
        
        actions, pending, metadata = await generator.generate_action(
            agent=agent,
            agent_type="rule_based",
            action_data=action_data
        )
        
        # Verify results
        assert len(actions) == 1
        assert len(pending) == 0
        assert actions[0].action_type == "QUOTE"
        assert actions[0].agent_id == "agent_001"
        assert actions[0].target_post_id == "post_123"
        assert len(actions[0].content) > 0
        assert metadata["generation_method"] == "rule_based"
    
    @pytest.mark.asyncio
    async def test_generate_llm_quote(self, generator, mock_llm_future):
        """Test LLM-based quote generation."""
        agent = {
            "id": "agent_002",
            "cluster_id": 1,
            "name": "TechUser",
            "interests": ["AI", "Technology"]
        }
        
        action_data = {
            "target_post_id": "post_456",
            "target_post_content": "Breaking: New AI model released!"
        }
        
        actions, pending, metadata = await generator.generate_action(
            agent=agent,
            agent_type="llm",
            action_data=action_data
        )
        
        # Verify LLM call was made
        assert len(actions) == 0  # No immediate actions
        assert len(pending) == 1  # One LLM call pending
        assert metadata["generation_method"] == "llm"
    
    @pytest.mark.asyncio
    async def test_missing_target_post(self, generator):
        """Test error handling when target post missing."""
        agent = {"id": "agent_003", "cluster_id": 1}
        action_data = {}  # Missing target_post_id
        
        actions, pending, metadata = await generator.generate_action(
            agent=agent,
            agent_type="rule_based",
            action_data=action_data
        )
        
        # Should return error
        assert len(actions) == 0
        assert "error" in metadata
```

### Step 8: Integration Test

Test end-to-end in simulation:

```python
# test_quote_integration.py

@pytest.mark.integration
async def test_quote_action_in_simulation(simulation_client):
    """Test QUOTE action in full simulation."""
    # Setup
    agent = simulation_client.agents["agent_001"]
    target_post_id = "post_123"
    
    # Simulate agent deciding to quote
    action_type = "QUOTE"
    action_data = {
        "target_post_id": target_post_id,
        "target_post_content": "Test post content"
    }
    
    # Execute action through client
    actions, pending, metadata = await simulation_client.dispatch_action_with_generator(
        action_type=action_type,
        agent=agent,
        agent_type="rule_based",
        action_data=action_data
    )
    
    # Verify action was created and submitted
    assert len(actions) == 1
    assert actions[0].action_type == "QUOTE"
    
    # Verify action reached server
    server_actions = simulation_client.server.get_actions_by_agent.remote(
        agent["id"]
    )
    server_actions = ray.get(server_actions)
    
    quote_actions = [a for a in server_actions if a["action_type"] == "QUOTE"]
    assert len(quote_actions) > 0
```

---

## Complete Example: Quote Action

Here's the complete implementation of a QUOTE action that allows agents to repost with commentary:

### File Structure
```
YSimulator/
├── YClient/
│   ├── action_generators/
│   │   ├── quote_generator.py (NEW - 250 lines)
│   │   └── factory.py (UPDATED - add QuoteGenerator)
│   ├── llm_utils/
│   │   └── llm_manager.py (UPDATED - add quote methods)
│   └── client.py (NO CHANGES)
├── YServer/
│   └── orchestrator_server.py (OPTIONAL - custom handler)
└── tests/
    └── test_quote_generator.py (NEW - 150 lines)
```

### Complete quote_generator.py

See Step 1 above for the complete implementation.

### Key Design Decisions

**Why separate LLM and rule-based?**
- Cost efficiency: LLM only for paid agents
- Fallback: Rule-based always available
- Testing: Easier to test deterministic rules

**Why use ActionContext?**
- Dependency injection: Easy to mock for tests
- Consistency: All generators use same pattern
- Flexibility: Easy to add new dependencies

**Why async/await?**
- Non-blocking LLM calls
- Better performance with many agents
- Consistent with Ray's actor model

---

## LLM Integration

### Using LLMManager (Phase 3)

All LLM operations go through `LLMManager`:

```python
# In your generator
async def generate_action(self, agent, agent_type, action_data):
    if agent_type == "llm":
        # Use LLMManager
        llm_future = await self.context.llm_manager.your_llm_method_async(
            llm_handle=self.context.llm_manager.llm_handle,
            cluster_id=agent["cluster_id"],
            agent_attrs=self._extract_agent_attributes(agent),
            # ... other params
        )
        
        return [], [llm_future], metadata
```

### Adding New LLM Methods

1. Add method to `llm_manager.py`:
```python
async def generate_your_content_async(
    self,
    llm_handle: ActorHandle,
    cluster_id: int,
    agent_attrs: dict,
    # ... your params
) -> ObjectRef:
    """Generate content using LLM."""
    prompt = self._create_your_prompt(cluster_id, agent_attrs, ...)
    
    future = llm_handle.generate.remote(
        prompt=prompt,
        max_tokens=200,
        temperature=0.7
    )
    
    return future
```

2. Create prompt helper:
```python
def _create_your_prompt(self, cluster_id, agent_attrs, ...):
    """Create prompt for your action."""
    persona = agent_attrs.get("persona", "User")
    
    prompt = f"""You are {agent_attrs['name']}, a {persona}.
    
Your task: ...

Output:"""
    
    return prompt
```

### LLM Best Practices

✅ **Do**:
- Use descriptive method names (`generate_quote_commentary_async`)
- Include agent persona in prompts
- Set appropriate temperature (0.7-0.9 for creativity)
- Limit max_tokens to control costs
- Handle LLM failures gracefully

❌ **Don't**:
- Call LLM directly from generators (use LLMManager)
- Block on LLM responses in generate_action (return futures)
- Use LLM for simple logic (use rules)
- Forget error handling

---

## Opinion Dynamics Integration

### When to Update Opinions

Update opinions for actions that express views on content:
- COMMENT (with opinion on post topic)
- LIKE/DISLIKE (implicit opinion)
- Your custom actions that evaluate content

### Using OpinionManager (Phase 4)

```python
# In your generator
async def generate_action(self, agent, agent_type, action_data):
    # Check if opinion dynamics enabled
    if self.context.is_opinion_dynamics_enabled_fn():
        # Get opinions for the content
        opinions = self.context.get_opinions_for_post_fn(
            target_post_id=action_data["target_post_id"]
        )
        
        # Calculate opinion updates
        opinion_updates = self.context.calculate_opinion_updates_fn(
            agent=agent,
            target_post_opinions=opinions,
            interaction_type="quote"  # Your action type
        )
        
        # Include in action
        action = ActionDTO(
            agent_id=agent["id"],
            cluster_id=agent["cluster_id"],
            action_type="QUOTE",
            content=content,
            target_post_id=action_data["target_post_id"],
            updated_opinions=opinion_updates  # Add here
        )
```

### Opinion Update Flow

```
1. Agent decides to interact with content
2. Generator retrieves content opinions via OpinionManager
3. OpinionManager calculates opinion updates (bounded confidence model)
4. Generator includes updated_opinions in ActionDTO
5. Server stores opinion updates
6. Opinions affect future recommendations
```

---

## Testing Strategy

### Unit Tests

Test each generator in isolation:

```python
# Test fixtures
@pytest.fixture
def mock_context():
    """Mock ActionContext."""
    return ActionContext(
        server=MagicMock(),
        llm_manager=MagicMock(),
        simulation_config={},
        agent_profiles={1: {"description": "Test"}},
        client_id="test",
        logger=logging.getLogger("test"),
        is_opinion_dynamics_enabled_fn=lambda: False,
        # ... other opinion functions
    )

# Test cases
def test_rule_based_generation(generator, mock_context):
    """Test rule-based action generation."""
    # ... test implementation

def test_llm_generation(generator, mock_context):
    """Test LLM-based action generation."""
    # ... test implementation

def test_error_handling(generator, mock_context):
    """Test error cases."""
    # ... test implementation
```

### Integration Tests

Test with real simulation client:

```python
@pytest.mark.integration
async def test_quote_in_simulation(simulation_client):
    """Test QUOTE action in full simulation."""
    # Setup
    agent = simulation_client.agents["agent_001"]
    
    # Execute
    result = await simulation_client.dispatch_action_with_generator(
        action_type="QUOTE",
        agent=agent,
        agent_type="rule_based",
        action_data={"target_post_id": "post_123"}
    )
    
    # Verify
    assert result is not None
```

### End-to-End Tests

Test complete simulation round:

```python
@pytest.mark.e2e
async def test_quote_in_simulation_round(simulation_setup):
    """Test QUOTE action in complete simulation round."""
    # Run simulation for one round
    simulation_setup.simulator.run_one_round()
    
    # Check for quote actions
    actions = simulation_setup.server.get_all_actions()
    quote_actions = [a for a in actions if a.action_type == "QUOTE"]
    
    assert len(quote_actions) > 0
```

---

## Troubleshooting

### Common Issues

#### 1. Action Not Appearing in Simulation

**Symptom**: Your action never gets executed.

**Causes**:
- Not added to ActionGeneratorFactory
- Not enabled in archetype configuration
- Action type string mismatch

**Solution**:
```python
# Check factory.py
self.generators = {
    "QUOTE": QuoteGenerator(context),  # Must be here
}

# Check activity_selector.py
archetype_actions = {
    "casual_user": {
        "QUOTE": 0.10,  # Must have probability > 0
    }
}
```

#### 2. LLM Not Being Called

**Symptom**: LLM method never executes.

**Causes**:
- Agent type not "llm"
- LLM method not awaited properly
- Future not returned correctly

**Solution**:
```python
# Correct pattern
if agent_type == "llm":
    future = await self.context.llm_manager.your_method_async(...)
    return [], [future], metadata  # Return future in pending list
```

#### 3. Opinion Updates Not Working

**Symptom**: Opinions don't change after action.

**Causes**:
- Opinion dynamics not enabled
- Opinion functions not called
- updated_opinions not included in ActionDTO

**Solution**:
```python
# Check configuration
if self.context.is_opinion_dynamics_enabled_fn():  # Check enabled
    opinion_updates = self.context.calculate_opinion_updates_fn(...)  # Calculate
    action.updated_opinions = opinion_updates  # Include in DTO
```

#### 4. Server Rejects Action

**Symptom**: Server returns error when action submitted.

**Causes**:
- Missing required fields in ActionDTO
- Invalid action_type string
- Server doesn't handle new action type

**Solution**:
```python
# Verify ActionDTO has all required fields
action = ActionDTO(
    agent_id=agent["id"],  # Required
    cluster_id=agent["cluster_id"],  # Required
    action_type="QUOTE",  # Required, must match server
    content=content,  # Usually required
    # ... other fields as needed
)
```

#### 5. Tests Failing

**Symptom**: Unit tests don't pass.

**Causes**:
- Mock context incomplete
- Async functions not awaited
- Assertions on wrong values

**Solution**:
```python
# Complete mock context
@pytest.fixture
def mock_context():
    return ActionContext(
        server=MagicMock(),  # All required fields
        llm_manager=MagicMock(),
        simulation_config={},
        agent_profiles={},
        client_id="test",
        logger=logging.getLogger("test"),
        # Don't forget opinion functions!
        is_opinion_dynamics_enabled_fn=lambda: False,
        calculate_opinion_updates_fn=lambda *args: {},
        # ... etc
    )

# Await async functions
@pytest.mark.asyncio
async def test_async_generation(generator):
    result = await generator.generate_action(...)  # Must await
```

### Debug Tips

**Enable detailed logging**:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Print action flow**:
```python
# In your generator
self.logger.info(f"Generating {action_type} for agent {agent_id}")
self.logger.debug(f"Action data: {action_data}")
self.logger.info(f"Generated action: {action}")
```

**Check server logs**:
```bash
# Server logs show received actions
grep "QUOTE" logs/server.log
```

**Verify factory routing**:
```python
# In test
factory = ActionGeneratorFactory(context)
generator = factory.get_generator("QUOTE")
assert isinstance(generator, QuoteGenerator)
```

---

## Next Steps

Once your action is working:

1. **Add to documentation**:
   - Update [AGENT_ACTIONS.md](../agents/AGENT_ACTIONS.md)
   - Add usage examples

2. **Performance testing**:
   - Measure action generation time
   - Check memory usage with many agents
   - Optimize if needed

3. **Monitor in production**:
   - Track action counts
   - Monitor LLM costs (if using LLM)
   - Check for errors/failures

4. **Iterate**:
   - Gather feedback from simulations
   - Refine action logic
   - Improve prompts (if LLM)

---

## Additional Resources

- **[Action Processor Framework](../architecture/ACTION_PROCESSOR_FRAMEWORK.md)** - Detailed architecture
- **[Phase 1 Refactoring Report](../refactoring/CLIENT_REFACTORING_REPORT.md#phase-1)** - Design decisions
- **[LLM Utilities](../architecture/LLM_UTILITIES_LAYER.md)** - LLM integration patterns
- **[Opinion Dynamics](../features/OPINION_DYNAMICS_ARCHITECTURE.md)** - Opinion integration
- **[Testing Guide](../development/TESTING.md)** - Comprehensive testing strategies

---

**Questions or Issues?**

- Check [Troubleshooting](#troubleshooting) section above
- Review [EXTENDING.md](EXTENDING.md) for general patterns
- Examine existing generators in `YClient/action_generators/`
- Open an issue on GitHub with `[Action Generator]` tag
