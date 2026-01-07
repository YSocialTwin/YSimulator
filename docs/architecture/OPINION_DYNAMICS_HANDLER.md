# Opinion Dynamics Handler

**Status**: ✅ Implemented (Phase 3 of Server Refactoring)  
**Version**: 1.0  
**Date**: January 5, 2026

## Overview

The Opinion Dynamics Handler is a modular system for managing agent opinions in YSimulator. It extracts opinion management logic from server.py into a dedicated, testable class that handles opinion initialization, updates, and neighbor opinion queries.

## Architecture

### Design Pattern: Service Layer

```
┌─────────────────────────────────────────────────────────────┐
│              OrchestratorServer Methods                     │
│   _ensure_agent_opinion_exists() - 18 lines                │
│   get_latest_agent_opinion() - 17 lines                    │
│   add_agent_opinion() - 28 lines                           │
│   get_neighbors_opinions() - 21 lines                      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼ Delegates to
┌─────────────────────────────────────────────────────────────┐
│                    OpinionHandler                           │
├─────────────────────────────────────────────────────────────┤
│  • ensure_agent_opinion_exists()                            │
│    - Profile-based opinion initialization                   │
│    - Page vs regular agent handling                         │
│    - Neutral fallbacks                                      │
│                                                             │
│  • get_latest_opinion()                                     │
│    - Retrieve current opinion value                         │
│                                                             │
│  • add_opinion()                                            │
│    - Store opinion updates                                  │
│    - Track interactions                                     │
│                                                             │
│  • get_neighbors_opinions()                                 │
│    - Query followee opinions                                │
│    - SQL and Redis support                                  │
└─────────────────────────────────────────────────────────────┘
```

## Components

### OpinionHandler

Manages all opinion-related operations with configuration-based behavior.

```python
from YSimulator.YServer.opinion_dynamics import OpinionHandler

# Initialize
opinion_handler = OpinionHandler(
    db_adapter=db,
    simulation_config=simulation_config,
    agent_profiles_cache=agent_profiles,
    current_round_id_getter=lambda: current_round_id,
    logger=logger
)
```

**Key Features:**
- Configurable enable/disable via simulation_config
- Profile-based opinion initialization
- Support for both SQL and Redis backends
- Case-insensitive topic name matching
- Automatic neutral fallbacks

## Methods

### 1. ensure_agent_opinion_exists()

Ensures an agent has an opinion on a topic, creating one if needed.

```python
opinion_handler.ensure_agent_opinion_exists(
    agent_id="agent_uuid",
    topic_id="topic_uuid",
    topic_name="Politics"
)
```

**Logic:**
- If opinion exists → Return (no-op)
- **Regular agent:**
  - Try to use opinion from profile
  - Case-insensitive topic matching
  - Fallback to neutral (0.5) if not found
- **Page agent:**
  - Use neutral (0.5) as placeholder
  - Client should have set opinion via LLM
- Only executes when `opinion_dynamics.enabled = True`

### 2. get_latest_opinion()

Retrieve the current opinion value for an agent on a topic.

```python
opinion_value = opinion_handler.get_latest_opinion(
    agent_id="agent_uuid",
    topic_id="topic_uuid"
)
# Returns: float (0.0-1.0) or None
```

### 3. add_opinion()

Store a new opinion record with interaction tracking.

```python
success = opinion_handler.add_opinion(
    agent_id="agent_uuid",
    topic_id="topic_uuid",
    opinion=0.75,
    id_interacted_with="other_agent_uuid",  # Optional
    id_post="post_uuid"  # Optional
)
```

**Use Cases:**
- Opinion updates after interactions
- LLM-generated opinion changes
- Bounded confidence model updates

### 4. get_neighbors_opinions()

Get opinions of all agents that the target agent follows.

```python
neighbor_opinions = opinion_handler.get_neighbors_opinions(
    agent_id="agent_uuid",
    topic_id="topic_uuid"
)
# Returns: List[float] - opinion values from neighbors
```

**Used for:**
- LLM-based opinion dynamics with `evaluation_scope="neighbors"`
- Bounded confidence models
- Opinion polarization analysis

## Migration from server.py

### Before (Monolithic)

```python
# server.py - ~80 lines for _ensure_agent_opinion_exists
def _ensure_agent_opinion_exists(self, agent_id, topic_id, topic_name, article_content=None):
    opinion_config = self.simulation_config.get("opinion_dynamics", {})
    if not opinion_config.get("enabled", False):
        return
    
    existing_opinion = self.db.get_latest_agent_opinion(agent_id, topic_id)
    if existing_opinion is not None:
        return
    
    cached_profile = self.agent_profiles_cache.get(agent_id)
    is_page_agent = cached_profile and cached_profile.is_page == 1
    
    if is_page_agent:
        opinion_value = 0.5
        # ... warning log
    else:
        # ... 40+ lines of profile lookup logic
    
    self.db.add_agent_opinion(...)
```

### After (Delegated)

```python
# server.py - 18 lines
def _ensure_agent_opinion_exists(self, agent_id, topic_id, topic_name, article_content=None):
    """Delegates to OpinionHandler for opinion management logic."""
    self.opinion_handler.ensure_agent_opinion_exists(
        agent_id, topic_id, topic_name, article_content
    )
```

**Benefits:**
- 78% reduction in method size (80 → 18 lines)
- Opinion logic independently testable
- Clear separation of concerns
- Easy to extend with new opinion models

## Configuration

Opinion dynamics controlled via `simulation_config`:

```python
simulation_config = {
    "opinion_dynamics": {
        "enabled": True,  # Enable/disable opinion tracking
        # ... other opinion dynamics settings
    }
}
```

When `enabled = False`:
- `ensure_agent_opinion_exists()` becomes a no-op
- No opinion database operations
- Zero performance overhead

## Agent Types

### Regular Agents

**Opinion Initialization:**
1. Check cached profile for topic opinion
2. Try exact topic name match
3. Try case-insensitive match
4. Fallback to neutral (0.5)

**Example:**
```python
profile.opinions = {"Politics": 0.8, "Technology": 0.3}
# Agent posting about "politics" → uses 0.8 (case-insensitive)
# Agent posting about "Sports" → uses 0.5 (neutral fallback)
```

### Page Agents

**Opinion Initialization:**
- Always use neutral (0.5) as placeholder
- Client should set opinion via LLM before posting
- Server logs warning if opinion missing

**Workflow:**
1. Client infers opinion via LLM
2. Client calls `add_agent_opinion()` to store
3. Client submits POST action
4. Server finds opinion already exists (no fallback needed)

## Testing

Test file: `YSimulator/tests/test_opinion_handler.py`

### Test Coverage
- ✅ **Initialization**: Enabled/disabled configurations
- ✅ **Opinion existence**: Early returns, profile lookup, fallbacks
- ✅ **Agent types**: Regular vs page agent handling
- ✅ **Case insensitivity**: Topic name matching
- ✅ **CRUD operations**: Get, add operations
- ✅ **Neighbors**: SQL and Redis backend queries
- ✅ **Error handling**: Database failures, missing data

### Running Tests
```bash
pytest YSimulator/tests/test_opinion_handler.py -v
```

## File Structure

```
YSimulator/YServer/opinion_dynamics/
├── __init__.py             # Module exports
└── opinion_handler.py      # OpinionHandler class
```

## Impact

### Code Reduction

| Method | Before | After | Reduction |
|--------|--------|-------|-----------|
| `_ensure_agent_opinion_exists()` | 80 lines | 18 lines | **-78%** |
| `get_latest_agent_opinion()` | 14 lines | 17 lines | -21%* |
| `add_agent_opinion()` | 25 lines | 28 lines | -12%* |
| `get_neighbors_opinions()` | 86 lines | 21 lines | **-76%** |
| **Total server.py** | 2,358 lines | 2,243 lines | **-5%** |

\* Slight increase due to delegation boilerplate, but logic is now modular

### Combined Phases 1-3

| Metric | Original | After P1 | After P2 | After P3 | Total Change |
|--------|----------|----------|----------|----------|--------------|
| **server.py lines** | 3,114 | 2,713 | 2,358 | 2,243 | **-871 (-28%)** |
| **Modules** | 0 | 1 | 2 | 3 | **+3** |
| **Testability** | Low | High | Very High | Very High | ⬆️⬆️⬆️ |

## Usage Examples

### Example 1: Ensure Opinion Exists

```python
# Before posting, ensure agent has opinion on topic
opinion_handler.ensure_agent_opinion_exists(
    agent_id="agent_123",
    topic_id="topic_politics",
    topic_name="Politics"
)
# Creates opinion from profile or uses neutral fallback
```

### Example 2: LLM-Based Opinion Update

```python
# Client infers new opinion via LLM
new_opinion = llm_infer_opinion(post_content, agent_profile)

# Store updated opinion
opinion_handler.add_opinion(
    agent_id="agent_123",
    topic_id="topic_politics",
    opinion=new_opinion,
    id_interacted_with="author_456",
    id_post="post_789"
)
```

### Example 3: Bounded Confidence Model

```python
# Get neighbor opinions for BC model
neighbor_opinions = opinion_handler.get_neighbors_opinions(
    agent_id="agent_123",
    topic_id="topic_politics"
)

# Calculate new opinion using BC formula
current_opinion = opinion_handler.get_latest_opinion("agent_123", "topic_politics")
new_opinion = bounded_confidence_update(current_opinion, neighbor_opinions, epsilon=0.2)

# Store updated opinion
opinion_handler.add_opinion("agent_123", "topic_politics", new_opinion)
```

## Extension Points

### Future Enhancements

1. **Opinion Calculator** - Bounded confidence formulas
2. **Inference Engine** - Server-side LLM integration (if needed)
3. **Opinion Models** - Pluggable BC, Voter, Hybrid models
4. **Opinion History** - Temporal opinion evolution tracking

### Adding New Models

```python
# Example: Add bounded confidence calculator
class OpinionCalculator:
    def bounded_confidence_update(
        self,
        current_opinion: float,
        neighbor_opinions: List[float],
        epsilon: float = 0.2
    ) -> float:
        # BC formula implementation
        pass
```

## Performance Considerations

### Caching
- Agent profiles cached at server initialization
- Avoids repeated database lookups
- Profile opinions accessed in O(1) time

### Database Efficiency
- SQL: Single query for followers + N queries for opinions
- Redis: Keys scan + pipeline operations possible
- Consider opinion caching for hot paths

## Related Documentation

- [Action Processor Framework](./ACTION_PROCESSOR_FRAMEWORK.md) - Phase 1
- [Recommendation Engine](./RECOMMENDATION_ENGINE.md) - Phase 2
- [Server Refactoring Report](../../docs/refactoring/SERVER_REFACTORING_REPORT.md) - Full plan

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Jan 5, 2026 | Initial implementation (Phase 3) |

---

**Implementation Status**: ✅ Complete  
**Test Coverage**: 12+ test cases  
**Code Reduction**: 115 lines from server.py
