# Recommendation Module

Modular recommendation engine for content and follow suggestions.

## Quick Start

```python
from YSimulator.YServer.recommendation import ContentRecommender, FollowRecommender

# Initialize recommenders
content_rec = ContentRecommender(db_adapter, visibility_rounds=36, logger=logger)
follow_rec = FollowRecommender(db_adapter, logger=logger)

# Get content recommendations
posts = content_rec.get_recommended_posts(
    agent_id="agent_uuid",
    mode="rchrono_popularity",
    limit=10,
    day=5,
    slot=12
)

# Get follow suggestions
users = follow_rec.get_follow_suggestions(
    agent_id="agent_uuid",
    mode="common_neighbors",
    n_neighbors=5
)
```

## Components

- **ContentRecommender** - Post recommendations with 10+ strategies
- **FollowRecommender** - User suggestions with 5 algorithms

## Documentation

See [RECOMMENDATION_ENGINE.md](../../docs/architecture/RECOMMENDATION_ENGINE.md) for detailed documentation.

## Testing

```bash
pytest YSimulator/tests/test_recommendation_engines.py -v
```
