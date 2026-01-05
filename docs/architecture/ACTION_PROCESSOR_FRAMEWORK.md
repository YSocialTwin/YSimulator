# Action Processor Framework

**Status**: ✅ Implemented (Phase 1 of Server Refactoring)  
**Version**: 1.0  
**Date**: January 5, 2026

## Overview

The Action Processor Framework is a modular system for handling agent actions in YSimulator. It uses the **Strategy Pattern** to separate action processing logic into dedicated, testable components, replacing the monolithic 476-line `submit_actions()` method with a clean, extensible architecture.

## Architecture

### Design Pattern: Strategy + Router

```
┌─────────────────────────────────────────────────────────┐
│              OrchestratorServer.submit_actions          │
│                      (70 lines)                         │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                    ActionRouter                         │
│  • Routes actions to appropriate processors             │
│  • Validates actions before processing                  │
│  • Supports custom processor registration               │
└─────────────────────────────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
┌───────────────────────┐   ┌───────────────────────┐
│  Specific Processors  │   │  Reaction Processor   │
│  • PostProcessor      │   │  (Default for other   │
│  • CommentProcessor   │   │   action types)       │
│  • ShareProcessor     │   │                       │
│  • FollowProcessor    │   │  Handles:             │
│  • UnfollowProcessor  │   │  • LIKE, LOVE         │
└───────────────────────┘   │  • ANGRY, SAD         │
                            │  • LAUGH, etc.        │
                            └───────────────────────┘
```

## Components

### 1. Base Classes (`base_processor.py`)

#### ActionContext
```python
@dataclass
class ActionContext:
    """Context information for action processing."""
    current_round_id: str
    day: int
    slot: int
```

Provides shared simulation state to all processors.

#### ActionResult
```python
@dataclass
class ActionResult:
    """Result of action processing."""
    success: bool
    action_type: str
    agent_id: str
    new_ids: List[str]        # Generated post IDs, etc.
    error: Optional[str]
    metadata: Dict[str, Any]
```

Standardized result format for all processors.

#### BaseActionProcessor
```python
class BaseActionProcessor(ABC):
    """Abstract base class for action processors."""
    
    def __init__(self, services: Any, logger: Optional[logging.Logger])
    
    @abstractmethod
    def process(self, action: Any, context: ActionContext) -> ActionResult
    
    def validate(self, action: Any) -> bool
```

All processors inherit from this base class.

### 2. Action Processors

Each processor handles one action type with full responsibility:

| Processor | Action Type | Responsibilities |
|-----------|-------------|------------------|
| **PostProcessor** | POST | • Create posts<br>• Handle article posts (with news_id)<br>• Handle image posts (with image_id)<br>• Manage topics and opinions<br>• Process annotations |
| **CommentProcessor** | COMMENT | • Create comments as posts<br>• Track thread hierarchy (thread_id)<br>• Increment reaction counts<br>• Handle parent sentiment<br>• Track user interests<br>• Store opinion updates |
| **ShareProcessor** | SHARE | • Create share posts<br>• Copy article references<br>• Add optional commentary<br>• Store opinion updates |
| **FollowProcessor** | FOLLOW | • Create follow relationships |
| **UnfollowProcessor** | UNFOLLOW | • Create unfollow relationships |
| **ReactionProcessor** | LIKE, LOVE, etc. | • Create reaction records<br>• Map reactions to sentiment<br>• Store sentiment per topic<br>• Track parent sentiment |

### 3. ActionRouter (`action_router.py`)

Central dispatcher for all actions:

```python
class ActionRouter:
    def __init__(self, services: Any, logger: Optional[logging.Logger])
    
    def route(self, action: Any, context: ActionContext) -> ActionResult
        """Route action to appropriate processor."""
    
    def register_processor(self, action_type: str, processor: BaseActionProcessor)
        """Register custom processor for action type."""
```

#### Routing Logic

1. Known action types (POST, COMMENT, SHARE, FOLLOW, UNFOLLOW) → Specific processor
2. Other action types (LIKE, LOVE, ANGRY, etc.) → ReactionProcessor (default)
3. Custom types → Registered custom processors

## Usage

### Basic Usage in OrchestratorServer

```python
def submit_actions(self, client_id: str, actions: list) -> None:
    """Submit actions using ActionRouter."""
    # Create context
    context = ActionContext(
        current_round_id=self.current_round_id,
        day=self.day,
        slot=self.slot
    )
    
    # Process each action
    for action in actions:
        result = self.action_router.route(action, context)
        if result.success and result.new_ids:
            new_ids.extend(result.new_ids)
```

### Registering Custom Processors

```python
# Create custom processor
class CustomActionProcessor(BaseActionProcessor):
    def process(self, action, context):
        # Custom logic
        return ActionResult(success=True, ...)

# Register it
router.register_processor("CUSTOM_ACTION", CustomActionProcessor(services, logger))
```

### Testing Individual Processors

```python
def test_post_processor():
    # Mock services
    mock_services = Mock()
    mock_services.add_post = Mock(return_value="post_123")
    
    # Create processor
    processor = PostProcessor(mock_services)
    
    # Create action and context
    action = Mock(agent_id="agent_1", content="Test post")
    context = ActionContext(current_round_id="round_1", day=1, slot=1)
    
    # Process and verify
    result = processor.process(action, context)
    assert result.success is True
    assert "post_123" in result.new_ids
```

## Benefits

### 1. Maintainability ✅
- **Small, focused classes**: Each processor has single responsibility
- **Easy to understand**: Clear separation of concerns
- **Simple debugging**: Isolated components are easier to trace

### 2. Testability ✅
- **Unit testable**: Each processor can be tested independently
- **Mock-friendly**: Simple interfaces require minimal mocking
- **High coverage**: Comprehensive test suite with 20+ test cases

### 3. Extensibility ✅
- **New action types**: Just create a new processor class
- **Custom logic**: Override process() method
- **Plugin architecture**: Register processors dynamically

### 4. Code Quality ✅
- **Reduced complexity**: submit_actions() from 476 to 70 lines (85% reduction)
- **Better organization**: Related code grouped together
- **Cleaner interfaces**: Standardized ActionResult format

## Migration Impact

### Before (Monolithic)
```python
def submit_actions(self, client_id: str, actions: list):
    for act in actions:
        if act.action_type == "POST":
            # 83 lines of POST logic
        elif act.action_type == "COMMENT":
            # 67 lines of COMMENT logic
        elif act.action_type == "SHARE":
            # 52 lines of SHARE logic
        # ... more action types
        else:
            # 89 lines of REACTION logic
    # Total: 476 lines
```

### After (Modular)
```python
def submit_actions(self, client_id: str, actions: list):
    context = ActionContext(self.current_round_id, self.day, self.slot)
    for act in actions:
        result = self.action_router.route(act, context)
        if result.success:
            new_ids.extend(result.new_ids)
    # Total: 70 lines
```

## File Structure

```
YSimulator/YServer/action_processors/
├── __init__.py                 # Module exports
├── base_processor.py           # Base classes (ActionContext, ActionResult, BaseActionProcessor)
├── action_router.py            # ActionRouter dispatcher
├── post_processor.py           # POST action handler
├── comment_processor.py        # COMMENT action handler
├── share_processor.py          # SHARE action handler
├── follow_processor.py         # FOLLOW action handler
├── unfollow_processor.py       # UNFOLLOW action handler
└── reaction_processor.py       # Reaction (LIKE, LOVE, etc.) handler
```

## Testing

Test file: `YSimulator/tests/test_action_processors.py`

### Test Coverage
- ✅ **PostProcessor**: Simple posts, article posts, topic posts
- ✅ **CommentProcessor**: Success cases, parent not found
- ✅ **ShareProcessor**: Success cases, original not found
- ✅ **FollowProcessor**: Success cases, database failures
- ✅ **UnfollowProcessor**: Basic functionality
- ✅ **ReactionProcessor**: LIKE reactions, sentiment mapping
- ✅ **ActionRouter**: Routing logic, custom processors

### Running Tests
```bash
pytest YSimulator/tests/test_action_processors.py -v
```

## Performance

- **No performance impact**: Same logic, just reorganized
- **Slightly better**: Reduced method call overhead
- **Memory efficient**: Processors are lightweight, shared instances

## Future Enhancements

### Potential Improvements
1. **Async processing**: Support for async action processing
2. **Batch operations**: Optimize batch action submission
3. **Pipeline stages**: Pre-processing, validation, post-processing hooks
4. **Event system**: Emit events for action completion
5. **Metrics collection**: Built-in performance monitoring

### Extension Points
- Custom validators per action type
- Action transformation pipeline
- Conditional routing based on agent properties
- Action queuing and prioritization

## Related Documentation

- [Server Refactoring Report](../refactoring/SERVER_REFACTORING_REPORT.md) - Full refactoring analysis
- [Repository Pattern](./REPOSITORY_PATTERN.md) - Data access layer
- [Architecture Overview](./ARCHITECTURE.md) - Overall system architecture

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Jan 5, 2026 | Initial implementation (Phase 1) |

---

**Implementation Status**: ✅ Complete  
**Test Coverage**: 20+ test cases  
**Code Reduction**: 85% (476 → 70 lines)
