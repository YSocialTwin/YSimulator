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
│  • 14 recommendation modes (including 4 new)                │
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
- `ReverseChrono` - Reverse chronological (newest first)
- `ReverseChronoPopularity` - Chronological with popularity boost
- `ReverseChronoFollowers` - Prioritize posts from followed users
- `ReverseChronoFollowersPopularity` - Followers + popularity
- `ReverseChronoComments` - Prioritize highly commented posts
- `CommonInterests` - Posts with common topic interests
- `CommonUserInterests` - Posts by users with common interests
- `SimilarUsersReactions` - Posts from similar users (by reactions)
- `SimilarUsersPosts` - Posts from similar users (by posting)
- `CollaborativeUserUser` - **NEW**: Collaborative filtering based on user-user similarity (finds users with high overlap in liked posts)
- `CollaborativeItemItem` - **NEW**: Collaborative filtering based on item-item similarity (finds posts often liked together)
- `ContentBasedFeatures` - **NEW**: Content-based filtering using feature extraction (hashtags, topics)
- `ContentBasedVector` - **NEW**: Content-based filtering using vector space similarity (preference vectors)

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

## New Recommendation Systems (Feb 2026)

### Collaborative Filtering

#### 1. User-User Collaborative Filtering (`CollaborativeUserUser`)

Finds users with a high overlap in liked posts and recommends posts they liked.

**How it works:**
1. Identifies the agent's liked posts
2. Finds other users who liked similar posts (high overlap)
3. Recommends posts liked by these similar users that the agent hasn't seen yet
4. Uses temporal window to respect visibility constraints

**Use Case**: "Users who like the same content as you also liked these posts"

**Example:**
```python
post_ids = content_recommender.get_recommended_posts(
    agent_id="agent123",
    mode="CollaborativeUserUser",
    limit=10,
    day=5,
    slot=12
)
```

#### 2. Item-Item Collaborative Filtering (`CollaborativeItemItem`)

Finds posts that are often liked together by the same groups of users.

**How it works:**
1. Identifies the agent's liked posts
2. For each liked post, finds users who also liked it
3. Discovers other posts those users liked (co-occurrence patterns)
4. Recommends posts with highest co-occurrence scores
5. Uses temporal window to respect visibility constraints

**Use Case**: "Posts that are frequently liked together with content you enjoyed"

**Example:**
```python
post_ids = content_recommender.get_recommended_posts(
    agent_id="agent123",
    mode="CollaborativeItemItem",
    limit=10,
    day=5,
    slot=12
)
```

### Content-Based Filtering

#### 3. Feature Extraction (`ContentBasedFeatures`)

Analyzes attributes of content the user has interacted with (topics, hashtags) and recommends similar posts.

**How it works:**
1. Extracts topics from posts the agent has liked
2. Builds a profile of preferred topics
3. Finds new posts with matching topics
4. Ranks by number of topic matches
5. Excludes already-reacted-to posts
6. Uses temporal window to respect visibility constraints

**Use Case**: "New posts about topics you're interested in"

**Example:**
```python
post_ids = content_recommender.get_recommended_posts(
    agent_id="agent123",
    mode="ContentBasedFeatures",
    limit=10,
    day=5,
    slot=12
)
```

#### 4. Vector Space Similarity (`ContentBasedVector`)

Recommends posts mathematically close to the user's "preference vector" using topic distributions.

**How it works:**
1. Builds a preference vector from liked posts' topics (weighted by frequency)
2. For each candidate post, creates a topic vector
3. Calculates similarity score (dot product of vectors)
4. Ranks posts by similarity to preference vector
5. Excludes already-reacted-to posts
6. Uses temporal window to respect visibility constraints

**Use Case**: "Posts that match your overall content preference profile"

**Example:**
```python
post_ids = content_recommender.get_recommended_posts(
    agent_id="agent123",
    mode="ContentBasedVector",
    limit=10,
    day=5,
    slot=12
)
```

### Temporal Window Implementation

All new recommender systems respect the temporal window pattern used throughout the system:

- Posts are only recommended if they fall within the visibility window
- Visibility is calculated as: `current_time - visibility_rounds`
- Both SQL and Redis implementations maintain this constraint
- This ensures realistic simulation of social media timelines

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
| 1.1 | Feb 4, 2026 | Added 4 new recommendation systems: CollaborativeUserUser, CollaborativeItemItem, ContentBasedFeatures, ContentBasedVector |

---

**Implementation Status**: ✅ Complete  
**Test Coverage**: 23+ test cases  
**Code Reduction**: 355 lines from server.py
**New Features**: 4 advanced recommendation algorithms (Collaborative & Content-Based Filtering)
