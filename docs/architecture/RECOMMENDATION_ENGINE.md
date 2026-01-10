# Recommendation Engine

**Status**: ✅ Implemented (Phase 2 of Server Refactoring)  
**Version**: 1.0  
**Date**: January 5, 2026

## Overview

The Recommendation Engine is a modular system for content and follow recommendations in YSimulator. It extracts recommendation logic from the monolithic server.py into dedicated, testable classes with pluggable strategies for different recommendation algorithms.

## Architecture

### Design Pattern: Strategy + Service Layer

```
┌─────────────────────────────────────────────────────────────┐
│              OrchestratorServer Methods                     │
│        get_recommended_posts() - 35 lines                   │
│        _get_follow_suggestions_*() - 13 lines each          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼ Delegates to
┌─────────────────────────────────────────────────────────────┐
│                 Recommendation Service Layer                │
├─────────────────────────────────────────────────────────────┤
│  ContentRecommender                                         │
│  • 10+ recommendation modes                                 │
│  • SQL and Redis backends                                   │
│  • Visibility filtering                                     │
│                                                             │
│  FollowRecommender                                          │
│  • 5 recommendation algorithms                              │
│  • SQL and Redis backends                                   │
│  • Political leaning bias                                   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼ Uses
┌─────────────────────────────────────────────────────────────┐
│                    recsys Module                            │
│  • content_recsys_db / content_recsys_redis                │
│  • follow_recsys_db / follow_recsys_redis                  │
│  • Strategy implementations                                 │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. ContentRecommender

Handles content (post) recommendations with multiple strategies.

```python
from YSimulator.YServer.recommendation import ContentRecommender

# Initialize
recommender = ContentRecommender(
    db_adapter=db,
    visibility_rounds=36,
    logger=logger
)

# Get recommendations
post_ids = recommender.get_recommended_posts(
    agent_id="agent_uuid",
    mode="rchrono_popularity",
    limit=10,
    followers_ratio=0.6,
    day=5,
    slot=12
)
```

**Supported Modes:**
- `random` - Random post ordering
- `rchrono` - Reverse chronological (newest first)
- `rchrono_popularity` - Chronological with popularity boost
- `rchrono_followers` - Prioritize posts from followed users
- `rchrono_followers_popularity` - Followers + popularity
- `rchrono_comments` - Prioritize highly commented posts
- `common_interests` - Posts with common topic interests
- `common_user_interests` - Posts by users with common interests
- `similar_users_react` - Posts from similar users (by reactions)
- `similar_users_posts` - Posts from similar users (by posting)

**Features:**
- Automatic visibility filtering based on simulation time
- Support for both SQL and Redis backends
- Efficient Redis pipeline operations
- Followers ratio control
- Excludes user's own posts

### 2. FollowRecommender

Handles follow (user) suggestions with network-based algorithms.

```python
from YSimulator.YServer.recommendation import FollowRecommender

# Initialize
recommender = FollowRecommender(
    db_adapter=db,
    logger=logger
)

# Get suggestions
user_ids = recommender.get_follow_suggestions(
    agent_id="agent_uuid",
    mode="common_neighbors",
    n_neighbors=5,
    leaning_bias=1
)
```

**Supported Modes:**
- `random` - Random user selection
- `common_neighbors` - Users with common followers
- `jaccard` - Jaccard similarity coefficient
- `adamic_adar` - Adamic-Adar index
- `preferential_attachment` - Based on follower count

**Features:**
- Political leaning bias support
- Excludes already-followed users
- Support for both SQL and Redis backends
- Fallback to random on errors

## Migration from server.py

### Before (Monolithic)

```python
# server.py - 254 lines for get_recommended_posts
def get_recommended_posts(self, agent_id, mode, limit, followers_ratio, client_id):
    # Calculate visibility
    visibility_day, visibility_hour = self._calculate_visibility_params(...)
    
    if self.db.use_redis:
        # 120 lines of Redis logic
        recent_posts_key = self.db._redis_key("posts", "recent")
        all_post_ids = self.db.redis_client.lrange(...)
        # ... fetch post data
        # ... filter posts
        # ... dispatch to strategy
        if mode == "rchrono":
            post_ids = content_recsys_redis.recommend_rchrono_redis(...)
        elif mode == "rchrono_popularity":
            # ... 10 more elif branches
    else:
        # 120 lines of SQL logic
        session = Session(self.db.engine)
        if mode == "rchrono":
            post_ids = content_recsys_db.recommend_rchrono(...)
        elif mode == "rchrono_popularity":
            # ... 10 more elif branches
    
    self._save_recommendation(agent_id, post_ids)
    return post_ids
```

### After (Delegated)

```python
# server.py - 35 lines
def get_recommended_posts(self, agent_id, mode, limit, followers_ratio, client_id):
    # Delegate to ContentRecommender
    post_ids = self.content_recommender.get_recommended_posts(
        agent_id=agent_id,
        mode=mode,
        limit=limit,
        followers_ratio=followers_ratio,
        day=self.day,
        slot=self.slot,
    )
    
    if post_ids:
        self._save_recommendation(agent_id, post_ids)
    
    return post_ids
```

**Benefits:**
- 86% reduction in method size (254 → 35 lines)
- Recommendation logic independently testable
- Clear separation of concerns
- Easier to add new strategies

## Testing

Test file: `YSimulator/tests/test_recommendation_engines.py`

### Test Coverage
- ✅ **ContentRecommender**: Initialization, SQL/Redis modes, visibility calculation, error handling
- ✅ **FollowRecommender**: Initialization, SQL/Redis modes, leaning bias, error handling  
- ✅ **Integration**: Both recommenders working together

### Running Tests
```bash
pytest YSimulator/tests/test_recommendation_engines.py -v
```

## File Structure

```
YSimulator/YServer/recommendation/
├── __init__.py                     # Module exports
├── content_recommender.py          # ContentRecommender class
└── follow_recommender.py           # FollowRecommender class
```

## Impact

### Code Reduction

| Component | Before | After | Reduction |
|-----------|--------|-------|-----------|
| `get_recommended_posts()` | 254 lines | 35 lines | **-86%** |
| `_get_follow_suggestions_sql()` | 107 lines | 13 lines | **-88%** |
| `_get_follow_suggestions_redis()` | 67 lines | 13 lines | **-81%** |
| **Total server.py** | 2,713 lines | 2,358 lines | **-13%** |

### Combined Phase 1 + Phase 2

| Metric | Original | After Phase 1 | After Phase 2 | Total Change |
|--------|----------|---------------|---------------|--------------|
| **server.py lines** | 3,114 | 2,713 | 2,358 | **-756 (-24%)** |
| **Largest method** | 476 lines | 70 lines | 70 lines | **-85%** |
| **Testability** | Low | High | Very High | ⬆️⬆️ |

## Usage Examples

### Example 1: Content Recommendations with Followers

```python
# Get posts from followed users with popularity boost
post_ids = content_recommender.get_recommended_posts(
    agent_id="agent123",
    mode="rchrono_followers_popularity",
    limit=20,
    followers_ratio=0.7,  # 70% from followers, 30% from others
    day=10,
    slot=15
)
```

### Example 2: Interest-Based Recommendations

```python
# Get posts with common topic interests
post_ids = content_recommender.get_recommended_posts(
    agent_id="agent123",
    mode="common_interests",
    limit=15,
    day=10,
    slot=15
)
```

### Example 3: Network-Based Follow Suggestions

```python
# Suggest users with common followers
user_ids = follow_recommender.get_follow_suggestions(
    agent_id="agent123",
    mode="common_neighbors",
    n_neighbors=10
)
```

### Example 4: Political Leaning Bias

```python
# Suggest users with similar political leaning
user_ids = follow_recommender.get_follow_suggestions(
    agent_id="agent123",
    mode="random",
    n_neighbors=10,
    leaning_bias=2  # Strong bias towards same leaning
)
```

## Extension Points

### Adding New Recommendation Strategies

1. **For Content**: Add new function in `content_recsys_db.py` or `content_recsys_redis.py`
2. **Update ContentRecommender**: Add new mode in `_get_recommendations_sql/redis()`
3. **Document**: Update mode list in this documentation

### Custom Recommendation Algorithms

Create custom strategy functions in the recsys module:

```python
# In content_recsys_db.py
def recommend_custom_strategy(session, agent_id, vis_day, vis_hour, limit):
    # Your custom logic here
    return post_ids
```

Then add to ContentRecommender:

```python
elif mode == "custom_strategy":
    return content_recsys_db.recommend_custom_strategy(
        session, agent_id, visibility_day, visibility_hour, limit
    )
```

## Performance Considerations

### Redis Backend
- Uses pipeline operations to minimize round trips
- Caches post metadata for efficient filtering
- Suitable for high-throughput scenarios

### SQL Backend
- Uses optimized queries with proper indexing
- Session management with proper cleanup
- Suitable for complex join operations

## Related Documentation

- [Action Processor Framework](./ACTION_PROCESSOR_FRAMEWORK.md) - Phase 1 refactoring
- [Server Refactoring Report](../../docs/refactoring/SERVER_REFACTORING_REPORT.md) - Full refactoring plan
- [Architecture Overview](./ARCHITECTURE.md) - System architecture

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Jan 5, 2026 | Initial implementation (Phase 2) |

---

**Implementation Status**: ✅ Complete  
**Test Coverage**: 15+ test cases  
**Code Reduction**: 355 lines from server.py
