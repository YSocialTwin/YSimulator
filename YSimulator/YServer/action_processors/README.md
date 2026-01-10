# Action Processors Module

Modular action processing framework using the Strategy pattern.

## Quick Start

```python
from YSimulator.YServer.action_processors import ActionRouter, ActionContext

# Initialize router with services
router = ActionRouter(services, logger)

# Create context
context = ActionContext(
    current_round_id="round_1",
    day=1,
    slot=1
)

# Process action
result = router.route(action, context)
if result.success:
    print(f"Action {result.action_type} processed successfully")
```

## Available Processors

- **PostProcessor** - Handles POST actions (articles, images, topics)
- **CommentProcessor** - Handles COMMENT actions (with threading)
- **ShareProcessor** - Handles SHARE actions (with article references)
- **FollowProcessor** - Handles FOLLOW actions
- **UnfollowProcessor** - Handles UNFOLLOW actions
- **ReactionProcessor** - Handles reactions (LIKE, LOVE, ANGRY, etc.)

## Architecture

Each processor:
1. Inherits from `BaseActionProcessor`
2. Implements `process(action, context) -> ActionResult`
3. Can optionally override `validate(action) -> bool`

## Documentation

See [ACTION_PROCESSOR_FRAMEWORK.md](../../docs/architecture/ACTION_PROCESSOR_FRAMEWORK.md) for detailed documentation.

## Testing

```bash
pytest YSimulator/tests/test_action_processors.py -v
```
