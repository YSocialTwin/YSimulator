# Extending Recommendation Systems in YSimulator

**Last Updated**: January 8, 2026  
**Architecture**: Service/Repository Pattern  
**Estimated Time**: 2-3 hours

---

## 📚 Quick Navigation

- **[← Documentation Index](../getting-started/INDEX.md)** - Complete documentation
- **[Recommendation Systems Overview](../features/RECOMMENDATION_SYSTEMS.md)** - Architecture details
- **[Service Integration](../architecture/SERVICE_INTEGRATION.md)** - Service layer patterns
- **[Repository Pattern](../architecture/REPOSITORY_PATTERN.md)** - Data access patterns

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [Adding Content Recommendation Modes](#adding-content-recommendation-modes)
4. [Adding Follow Recommendation Modes](#adding-follow-recommendation-modes)
5. [Complete Example: Interest Graph](#complete-example-interest-graph)
6. [Redis Integration](#redis-integration)
7. [Testing Strategy](#testing-strategy)
8. [Best Practices](#best-practices)

---

## Quick Start

**Goal**: Add a new recommendation algorithm in ~1 hour.

**Steps**:
1. Choose recommendation type (content or follow)
2. Implement algorithm method in service class
3. Add Redis caching (optional but recommended)
4. Update configuration
5. Test the algorithm

**Result**: A new recommendation mode available for agents.

---

## Architecture Overview

### Recommendation System Structure

```
Agent → Server → RecommendationService → Repository → Database
                        ↓
                  Redis Cache (optional)
```

**Key Components**:
- `RecommendationService`: Business logic for recommendations
- `SQLRepository`: SQL queries for complex operations
- `RedisRepository`: Fast caching layer
- `DatabaseServiceAdapter`: Unified interface

### Current Recommendation Modes

**Content Recommendations** (10 modes):
- `recent`: Chronological order
- `random`: Random selection
- `interest_based`: Match agent interests
- `popular`: By engagement metrics
- `network_based`: From followed users
- `trending`: Recent + popular
- `explore`: Diversity-focused
- `personalized`: Multi-factor scoring
- `opinion_aware`: Opinion dynamics integration
- `hybrid`: Weighted combination

**Follow Recommendations** (5 modes):
- `random`: Random users
- `popular`: By follower count
- `similar`: Similar interests
- `friend_of_friend`: Social graph
- `active`: By activity level

### Service Layer Pattern

All recommendation logic goes through services:

```python
class RecommendationService:
    """Service for content and follow recommendations."""
    
    def __init__(self, db_adapter, redis_client=None):
        self.db = db_adapter
        self.redis = redis_client
    
    def get_content_recommendations(
        self,
        user_id: str,
        mode: str,
        limit: int = 10,
        **kwargs
    ) -> List[dict]:
        """Get content recommendations for user."""
        # Route to appropriate algorithm
        if mode == "recent":
            return self._recommend_recent(user_id, limit)
        elif mode == "your_new_mode":
            return self._recommend_your_new_mode(user_id, limit, **kwargs)
        # ... etc
```

---

## Adding Content Recommendation Modes

### Step 1: Implement Algorithm Method

Add method to `YServer/services/recommendation_service.py`:

```python
def _recommend_interest_graph(
    self,
    user_id: str,
    limit: int = 10,
    depth: int = 2,
    **kwargs
) -> List[dict]:
    """
    Recommend content using interest graph traversal.
    
    Algorithm:
    1. Get user's interests
    2. Find users with similar interests (depth levels)
    3. Get their recent posts
    4. Rank by interest overlap + recency
    
    Args:
        user_id: Target user ID
        limit: Max recommendations
        depth: Graph traversal depth (1-3)
    
    Returns:
        List of post dicts with scores
    """
    # Try Redis first for performance
    if self.redis:
        cached = self._get_cached_interest_graph_recommendations(
            user_id, limit, depth
        )
        if cached:
            return cached
    
    # Get user interests
    user = self.db.get_user_by_id(user_id)
    if not user or not user.get("interests"):
        # Fallback to recent
        return self._recommend_recent(user_id, limit)
    
    user_interests = set(user["interests"])
    
    # Find similar users (multi-level)
    similar_users = self._find_similar_users_by_interest(
        user_interests,
        depth=depth,
        max_users=50
    )
    
    # Get their recent posts
    candidate_posts = []
    for similar_user_id in similar_users:
        posts = self.db.get_posts_by_user(
            similar_user_id,
            limit=20,
            order_by="created_at DESC"
        )
        candidate_posts.extend(posts)
    
    # Remove already seen posts
    seen_post_ids = self._get_seen_posts(user_id)
    candidate_posts = [
        p for p in candidate_posts
        if p["post_id"] not in seen_post_ids
    ]
    
    # Score and rank posts
    scored_posts = self._score_posts_by_interest_graph(
        candidate_posts,
        user_interests=user_interests,
        similar_users=similar_users
    )
    
    # Sort by score and limit
    scored_posts.sort(key=lambda x: x["score"], reverse=True)
    recommendations = scored_posts[:limit]
    
    # Cache for future requests
    if self.redis:
        self._cache_interest_graph_recommendations(
            user_id, recommendations, depth, ttl=300
        )
    
    return recommendations

def _find_similar_users_by_interest(
    self,
    user_interests: set,
    depth: int = 2,
    max_users: int = 50
) -> List[str]:
    """
    Find users with similar interests using BFS traversal.
    
    Args:
        user_interests: Set of interest strings
        depth: How many levels to traverse
        max_users: Maximum users to return
    
    Returns:
        List of user IDs sorted by similarity
    """
    # Level 1: Direct interest matches
    level1_users = []
    for interest in user_interests:
        users = self.db.get_users_by_interest(interest, limit=20)
        level1_users.extend([u["user_id"] for u in users])
    
    level1_users = list(set(level1_users))  # Deduplicate
    
    if depth == 1:
        return level1_users[:max_users]
    
    # Level 2: Friends of friends (interest graph)
    level2_users = set()
    for user_id in level1_users[:20]:  # Limit to avoid explosion
        user = self.db.get_user_by_id(user_id)
        if user and user.get("interests"):
            for interest in user["interests"]:
                if interest not in user_interests:  # New interests
                    users = self.db.get_users_by_interest(interest, limit=10)
                    level2_users.update([u["user_id"] for u in users])
    
    # Combine and rank by overlap
    all_users = level1_users + list(level2_users)
    ranked_users = self._rank_users_by_interest_similarity(
        all_users, user_interests
    )
    
    return ranked_users[:max_users]

def _score_posts_by_interest_graph(
    self,
    posts: List[dict],
    user_interests: set,
    similar_users: List[str]
) -> List[dict]:
    """
    Score posts based on interest graph signals.
    
    Scoring factors:
    - Interest overlap (0-1)
    - User similarity rank (0-1)
    - Recency (0-1)
    - Engagement (0-1)
    
    Args:
        posts: Candidate posts
        user_interests: Target user's interests
        similar_users: Ranked list of similar users
    
    Returns:
        Posts with added 'score' field
    """
    now = datetime.now()
    user_similarity_map = {
        uid: 1.0 - (i / len(similar_users))
        for i, uid in enumerate(similar_users)
    }
    
    scored_posts = []
    for post in posts:
        # Interest overlap score
        post_topics = set(post.get("topics", []))
        interest_overlap = len(post_topics & user_interests) / max(len(user_interests), 1)
        
        # User similarity score
        author_id = post["user_id"]
        similarity_score = user_similarity_map.get(author_id, 0.0)
        
        # Recency score (decay over 7 days)
        age_hours = (now - post["created_at"]).total_seconds() / 3600
        recency_score = max(0, 1.0 - (age_hours / 168))  # 168 hours = 7 days
        
        # Engagement score
        total_engagement = (
            post.get("like_count", 0) +
            post.get("comment_count", 0) * 2 +
            post.get("share_count", 0) * 3
        )
        engagement_score = min(1.0, total_engagement / 100)
        
        # Weighted combination
        final_score = (
            interest_overlap * 0.4 +
            similarity_score * 0.3 +
            recency_score * 0.2 +
            engagement_score * 0.1
        )
        
        post["score"] = final_score
        scored_posts.append(post)
    
    return scored_posts

def _rank_users_by_interest_similarity(
    self,
    user_ids: List[str],
    target_interests: set
) -> List[str]:
    """Rank users by interest similarity to target."""
    user_scores = []
    
    for user_id in user_ids:
        user = self.db.get_user_by_id(user_id)
        if not user or not user.get("interests"):
            continue
        
        user_interests = set(user["interests"])
        overlap = len(user_interests & target_interests)
        similarity = overlap / max(len(target_interests), 1)
        
        user_scores.append((user_id, similarity))
    
    # Sort by similarity
    user_scores.sort(key=lambda x: x[1], reverse=True)
    return [user_id for user_id, _ in user_scores]
```

### Step 2: Add Redis Caching

Implement caching methods:

```python
def _get_cached_interest_graph_recommendations(
    self,
    user_id: str,
    limit: int,
    depth: int
) -> Optional[List[dict]]:
    """Get cached recommendations from Redis."""
    if not self.redis:
        return None
    
    cache_key = f"recsys:interest_graph:{user_id}:{depth}:{limit}"
    
    try:
        cached_data = self.redis.get(cache_key)
        if cached_data:
            return json.loads(cached_data)
    except Exception as e:
        self.logger.warning(f"Redis get failed: {e}")
    
    return None

def _cache_interest_graph_recommendations(
    self,
    user_id: str,
    recommendations: List[dict],
    depth: int,
    ttl: int = 300
):
    """Cache recommendations in Redis."""
    if not self.redis:
        return
    
    cache_key = f"recsys:interest_graph:{user_id}:{depth}:{len(recommendations)}"
    
    try:
        self.redis.setex(
            cache_key,
            ttl,
            json.dumps(recommendations, default=str)
        )
    except Exception as e:
        self.logger.warning(f"Redis set failed: {e}")
```

### Step 3: Update Mode Routing

Update the main routing method:

```python
def get_content_recommendations(
    self,
    user_id: str,
    mode: str,
    limit: int = 10,
    **kwargs
) -> List[dict]:
    """Get content recommendations."""
    try:
        if mode == "recent":
            return self._recommend_recent(user_id, limit)
        elif mode == "interest_graph":  # Add here
            return self._recommend_interest_graph(
                user_id, limit, depth=kwargs.get("depth", 2)
            )
        elif mode == "random":
            return self._recommend_random(user_id, limit)
        # ... other modes
        else:
            self.logger.warning(f"Unknown mode: {mode}, using 'recent'")
            return self._recommend_recent(user_id, limit)
    
    except Exception as e:
        self.logger.error(f"Recommendation error: {e}")
        # Fallback to safe default
        return self._recommend_recent(user_id, limit)
```

### Step 4: Add Configuration

Update `config/simulation_config.yaml`:

```yaml
recommendations:
  content:
    mode: "interest_graph"  # New mode
    interest_graph:
      depth: 2  # Graph traversal depth
      max_candidates: 50
      cache_ttl: 300  # 5 minutes
    limit: 10
  
  follow:
    mode: "similar"
    limit: 5
```

### Step 5: Test the Algorithm

```python
# tests/test_recommendation_service.py

class TestInterestGraphRecommendation:
    
    def test_interest_graph_basic(self, db_adapter, mock_redis):
        """Test basic interest graph recommendations."""
        service = RecommendationService(db_adapter, mock_redis)
        
        # Setup test data
        user_id = "user_001"
        
        # Get recommendations
        recommendations = service.get_content_recommendations(
            user_id=user_id,
            mode="interest_graph",
            limit=10,
            depth=2
        )
        
        # Verify
        assert len(recommendations) <= 10
        assert all("post_id" in p for p in recommendations)
        assert all("score" in p for p in recommendations)
        
        # Verify sorted by score
        scores = [p["score"] for p in recommendations]
        assert scores == sorted(scores, reverse=True)
    
    def test_interest_graph_caching(self, db_adapter, redis_client):
        """Test Redis caching."""
        service = RecommendationService(db_adapter, redis_client)
        
        user_id = "user_002"
        
        # First call - populates cache
        recs1 = service.get_content_recommendations(
            user_id=user_id,
            mode="interest_graph",
            limit=10
        )
        
        # Second call - from cache
        recs2 = service.get_content_recommendations(
            user_id=user_id,
            mode="interest_graph",
            limit=10
        )
        
        # Should be identical
        assert recs1 == recs2
        
        # Verify Redis was used
        cache_key = f"recsys:interest_graph:{user_id}:2:10"
        assert redis_client.exists(cache_key)
    
    def test_interest_graph_fallback(self, db_adapter):
        """Test fallback when user has no interests."""
        service = RecommendationService(db_adapter)
        
        # User with no interests
        user_id = "user_new"
        
        recommendations = service.get_content_recommendations(
            user_id=user_id,
            mode="interest_graph",
            limit=10
        )
        
        # Should fallback to 'recent'
        assert len(recommendations) > 0
```

---

## Adding Follow Recommendation Modes

### Step 1: Implement Algorithm

Add method to `recommendation_service.py`:

```python
def _recommend_follows_community_detection(
    self,
    user_id: str,
    limit: int = 5
) -> List[dict]:
    """
    Recommend users to follow using community detection.
    
    Algorithm:
    1. Get user's current network
    2. Detect communities in network
    3. Recommend popular users from same community
    4. Balance with cross-community suggestions
    
    Returns:
        List of user dicts with scores
    """
    # Get user's network
    following = self.db.get_following(user_id)
    if len(following) < 3:
        # Not enough data, fallback to popular
        return self._recommend_follows_popular(user_id, limit)
    
    # Detect user's community
    user_community = self._detect_user_community(user_id, following)
    
    # Get candidates from same community
    same_community = self._get_community_members(
        user_community,
        exclude=[user_id] + following,
        limit=limit * 2
    )
    
    # Get some cross-community candidates
    other_communities = self._get_other_communities(user_community)
    cross_community = []
    for community_id in other_communities[:2]:
        members = self._get_community_members(
            community_id,
            exclude=[user_id] + following,
            limit=3
        )
        cross_community.extend(members)
    
    # Combine and score
    candidates = same_community + cross_community
    scored_users = self._score_follow_candidates(
        candidates,
        user_id=user_id,
        same_community=same_community
    )
    
    # Sort and limit
    scored_users.sort(key=lambda x: x["score"], reverse=True)
    return scored_users[:limit]
```

### Step 2: Add Helper Methods

```python
def _detect_user_community(
    self,
    user_id: str,
    following: List[str]
) -> str:
    """Detect which community user belongs to."""
    # Simple approach: most common community among followings
    community_counts = {}
    
    for followed_id in following:
        user = self.db.get_user_by_id(followed_id)
        if user and "community_id" in user:
            community_id = user["community_id"]
            community_counts[community_id] = community_counts.get(community_id, 0) + 1
    
    if not community_counts:
        return "default"
    
    # Return most common
    return max(community_counts.items(), key=lambda x: x[1])[0]

def _get_community_members(
    self,
    community_id: str,
    exclude: List[str],
    limit: int = 10
) -> List[dict]:
    """Get members of a community."""
    members = self.db.get_users_by_community(community_id, limit=limit * 2)
    
    # Filter out excluded users
    filtered = [m for m in members if m["user_id"] not in exclude]
    
    return filtered[:limit]

def _score_follow_candidates(
    self,
    candidates: List[dict],
    user_id: str,
    same_community: List[dict]
) -> List[dict]:
    """Score follow candidates."""
    same_community_ids = set(u["user_id"] for u in same_community)
    
    for user in candidates:
        # Community bonus
        community_score = 1.0 if user["user_id"] in same_community_ids else 0.3
        
        # Popularity score
        follower_count = user.get("follower_count", 0)
        popularity_score = min(1.0, follower_count / 1000)
        
        # Activity score
        post_count = user.get("post_count", 0)
        activity_score = min(1.0, post_count / 100)
        
        # Combined score
        user["score"] = (
            community_score * 0.5 +
            popularity_score * 0.3 +
            activity_score * 0.2
        )
    
    return candidates
```

### Step 3: Update Routing

```python
def get_follow_recommendations(
    self,
    user_id: str,
    mode: str,
    limit: int = 5,
    **kwargs
) -> List[dict]:
    """Get follow recommendations."""
    try:
        if mode == "random":
            return self._recommend_follows_random(user_id, limit)
        elif mode == "popular":
            return self._recommend_follows_popular(user_id, limit)
        elif mode == "community_detection":  # Add here
            return self._recommend_follows_community_detection(user_id, limit)
        # ... other modes
    except Exception as e:
        self.logger.error(f"Follow recommendation error: {e}")
        return self._recommend_follows_random(user_id, limit)
```

---

## Complete Example: Interest Graph

See Step 1 in [Adding Content Recommendation Modes](#adding-content-recommendation-modes) for the complete working implementation of an interest graph recommendation algorithm.

**Key Features**:
- Multi-level graph traversal
- Interest similarity scoring
- Redis caching for performance
- Graceful fallbacks
- Comprehensive scoring (4 factors)

**Performance**:
- SQL queries: 3-5 (depending on depth)
- Redis hits: 1 (if cached)
- Latency: ~50ms (cached), ~200ms (cold)
- Cache TTL: 5 minutes

---

## Redis Integration

### Why Redis?

✅ **Performance**: 100x faster than SQL for simple lookups  
✅ **Scalability**: Handles high request rates  
✅ **Caching**: Reduces database load  
✅ **Flexibility**: Easy to add/remove

### Redis Patterns

**1. Simple Caching**:
```python
def get_recommendations_cached(self, user_id, mode, limit):
    cache_key = f"recsys:{mode}:{user_id}:{limit}"
    
    # Try cache first
    cached = self.redis.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Generate recommendations
    recommendations = self._generate_recommendations(user_id, mode, limit)
    
    # Cache for 5 minutes
    self.redis.setex(cache_key, 300, json.dumps(recommendations))
    
    return recommendations
```

**2. Set-Based Caching** (for user lists):
```python
def get_similar_users_cached(self, user_id):
    cache_key = f"recsys:similar:{user_id}"
    
    # Try Redis set
    similar_ids = self.redis.smembers(cache_key)
    if similar_ids:
        return list(similar_ids)
    
    # Calculate similar users
    similar_ids = self._find_similar_users(user_id)
    
    # Cache as set
    if similar_ids:
        self.redis.sadd(cache_key, *similar_ids)
        self.redis.expire(cache_key, 600)  # 10 minutes
    
    return similar_ids
```

**3. Sorted Sets** (for ranked recommendations):
```python
def get_trending_posts_cached(self, limit):
    cache_key = "recsys:trending"
    
    # Try Redis sorted set
    trending = self.redis.zrevrange(cache_key, 0, limit-1, withscores=True)
    if trending:
        return [(post_id.decode(), score) for post_id, score in trending]
    
    # Calculate trending posts
    trending = self._calculate_trending_posts()
    
    # Cache as sorted set
    if trending:
        for post_id, score in trending:
            self.redis.zadd(cache_key, {post_id: score})
        self.redis.expire(cache_key, 300)  # 5 minutes
    
    return trending[:limit]
```

### Graceful Degradation

Always handle Redis failures:

```python
def get_recommendations(self, user_id, mode, limit):
    # Try Redis cache
    if self.redis:
        try:
            cached = self._get_cached_recommendations(user_id, mode, limit)
            if cached:
                return cached
        except Exception as e:
            self.logger.warning(f"Redis error: {e}, falling back to SQL")
    
    # Fall back to SQL
    return self._generate_recommendations_sql(user_id, mode, limit)
```

---

## Testing Strategy

### Unit Tests

Test each algorithm in isolation:

```python
def test_interest_graph_algorithm():
    """Test interest graph logic."""
    # Mock dependencies
    db_adapter = MockDatabaseAdapter()
    service = RecommendationService(db_adapter)
    
    # Test algorithm
    recommendations = service._recommend_interest_graph(
        user_id="test_user",
        limit=10,
        depth=2
    )
    
    # Verify output
    assert len(recommendations) <= 10
    assert all("score" in r for r in recommendations)
```

### Integration Tests

Test with real database:

```python
@pytest.mark.integration
def test_interest_graph_with_db():
    """Test with real database."""
    # Setup test database
    db = setup_test_database()
    service = RecommendationService(db)
    
    # Test recommendations
    recommendations = service.get_content_recommendations(
        user_id="user_001",
        mode="interest_graph",
        limit=10
    )
    
    # Verify
    assert len(recommendations) > 0
```

### Performance Tests

Test algorithm performance:

```python
@pytest.mark.performance
def test_interest_graph_performance():
    """Test recommendation performance."""
    service = RecommendationService(db, redis)
    
    # Warm up cache
    service.get_content_recommendations("user_001", "interest_graph", 10)
    
    # Measure cached performance
    start = time.time()
    for _ in range(100):
        service.get_content_recommendations("user_001", "interest_graph", 10)
    duration = time.time() - start
    
    # Should be < 5ms per request with cache
    assert duration / 100 < 0.005
```

---

## Best Practices

### Algorithm Design

✅ **Do**:
- Start simple, iterate based on metrics
- Consider computational complexity (O(n) or better)
- Include fallback logic for edge cases
- Use caching for expensive operations
- Score with multiple factors (interest, recency, popularity, etc.)

❌ **Don't**:
- Implement O(n²) algorithms for large datasets
- Ignore user privacy (don't leak private info in recommendations)
- Forget to filter out already-seen content
- Hard-code parameters (use configuration)

### Scoring Best Practices

✅ **Normalize scores** to [0, 1] range:
```python
score = min(1.0, raw_value / max_value)
```

✅ **Use weighted combinations**:
```python
final_score = (
    interest_score * 0.4 +
    recency_score * 0.3 +
    popularity_score * 0.2 +
    diversity_score * 0.1
)
```

✅ **Log score components** for debugging:
```python
self.logger.debug(
    f"Post {post_id} scores: "
    f"interest={interest_score:.2f}, "
    f"recency={recency_score:.2f}, "
    f"final={final_score:.2f}"
)
```

### Performance Optimization

**1. Use database indexes**:
```sql
CREATE INDEX idx_posts_created_at ON posts(created_at DESC);
CREATE INDEX idx_posts_user_id ON posts(user_id);
CREATE INDEX idx_user_interests ON user_interests(interest);
```

**2. Limit query results**:
```python
# Good: Limit at database level
posts = db.query("SELECT * FROM posts ORDER BY created_at DESC LIMIT 100")

# Bad: Load all then slice
posts = db.query("SELECT * FROM posts ORDER BY created_at DESC")[:100]
```

**3. Batch operations**:
```python
# Good: Batch fetch
user_ids = [p["user_id"] for p in posts]
users = db.get_users_batch(user_ids)

# Bad: N+1 queries
for post in posts:
    user = db.get_user(post["user_id"])
```

### Error Handling

Always provide fallbacks:

```python
def get_content_recommendations(self, user_id, mode, limit):
    try:
        if mode == "your_mode":
            return self._recommend_your_mode(user_id, limit)
    except Exception as e:
        self.logger.error(f"Recommendation error: {e}")
        # Safe fallback
        return self._recommend_recent(user_id, limit)
```

---

## Additional Resources

- **[Recommendation Systems Overview](../features/RECOMMENDATION_SYSTEMS.md)** - Architecture and modes
- **[Service Integration](../architecture/SERVICE_INTEGRATION.md)** - Service layer patterns
- **[Repository Pattern](../architecture/REPOSITORY_PATTERN.md)** - Data access best practices
- **[Redis Integration](../data-storage/RECSYS_REDIS_SUPPORT.md)** - Redis optimization guide

---

**Questions or Issues?**

- Review existing recommendation modes in `YServer/services/recommendation_service.py`
- Check performance benchmarks in `docs/data-storage/RECSYS_REDIS_SUPPORT.md`
- Open an issue on GitHub with `[Recommendation]` tag
