# Redis Recommendation Systems Integration

**Version:** 3.0  
**Last Updated:** January 9, 2026  
**Status:** Production-Ready with Hybrid Approach  

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Recommendation Modes](#recommendation-modes)
4. [Implementation Details](#implementation-details)
5. [Performance Analysis](#performance-analysis)
6. [Migration Path](#migration-path)
7. [Best Practices](#best-practices)

---

## Overview

YSimulator implements 10 distinct recommendation algorithms, each optimized for different use cases. The system uses a **hybrid approach** combining Redis for high-performance operations with SQL for complex queries.

### Recommendation Coverage

| Type | Redis | Hybrid | SQL | Total |
|------|-------|--------|-----|-------|
| Content | 3 | 4 | 0 | 7 |
| Follow | 2 | 1 | 0 | 3 |
| **Total** | **5** | **5** | **0** | **10** |

### Architecture Grade: **B+**

**Strengths:**
- High-performance pure Redis modes
- Graceful fallback for complex algorithms
- Flexible cache-first approach
- Good separation of concerns

**Enhancement Opportunities:**
- More Redis-native similarity calculations
- Pre-computed recommendation caches
- Redis Streams for real-time updates

---

## Architecture

### System Flow

```
Client Request
     ↓
RecommendationService
     ↓
Mode Selection
     ├─ Pure Redis Modes (50%)
     │   ├─ random
     │   ├─ rchrono
     │   ├─ rchrono_popularity
     │   ├─ rchrono_comments
     │   └─ (Fast: <5ms)
     │
     └─ Hybrid Modes (50%)
         ├─ rchrono_followers (SQL follow + Redis posts)
         ├─ rchrono_followers_popularity
         ├─ common_interests (Redis sets + SQL fallback)
         ├─ common_user_interests
         └─ similar_users (SQL demographics + Redis filtering)
```

### Data Flow Pattern

**Pure Redis Mode:**
```
1. Fetch posts from Redis (ysim:posts:recent)
2. Filter based on criteria (all in Redis)
3. Sort and rank (in-memory)
4. Return recommendations
```

**Hybrid Mode:**
```
1. Fetch relationship/metadata from SQL (e.g., follows)
2. Get candidate posts from Redis
3. Apply filters using Redis data
4. Combine and rank results
5. Return recommendations
```

---

## Recommendation Modes

### Content Recommendations

#### 1. Random (`random`)

**Redis Implementation:** ✅ **100%**

**Algorithm:**
```python
# Pseudocode
recent_posts = redis.lrange("ysim:posts:recent", 0, -1)
filtered_posts = [p for p in recent_posts if p.user_id != agent_id]
random.shuffle(filtered_posts)
return filtered_posts[:limit]
```

**Performance:** Sub-millisecond
**Use Case:** Baseline, exploration, diversity

---

#### 2. Reverse Chronological (`rchrono`)

**Redis Implementation:** ✅ **100%**

**Algorithm:**
```python
# Most recent posts first
recent_posts = redis.lrange("ysim:posts:recent", 0, limit*2)
filtered = [p for p in recent_posts if p.user_id != agent_id]
return filtered[:limit]
```

**Redis Data Structures:**
- `ysim:posts:recent` - List (LPUSH for newest first)

**Performance:** ~1ms for 100 posts
**Use Case:** Twitter-style timeline, news feeds

---

#### 3. Popularity-Weighted (`rchrono_popularity`)

**Redis Implementation:** ✅ **100%**

**Algorithm:**
```python
# Recent posts sorted by engagement
recent_posts = redis.lrange("ysim:posts:recent", 0, limit*5)
posts_with_scores = []

for post_id in recent_posts:
    post_data = redis.hgetall(f"ysim:post:{post_id}")
    reaction_count = int(post_data.get("reaction_count", 0))
    posts_with_scores.append((post_id, reaction_count))

# Sort by reactions (descending)
sorted_posts = sorted(posts_with_scores, key=lambda x: -x[1])
return [p[0] for p in sorted_posts[:limit]]
```

**Redis Data Structures:**
- `ysim:post:{id}` - Hash with `reaction_count` field
- `ysim:posts:recent` - List of recent post IDs

**Performance:** ~2-3ms for 100 posts
**Use Case:** Trending content, viral posts

---

#### 4. Follower-Based (`rchrono_followers`)

**Redis Implementation:** 🔄 **Hybrid** (70% Redis, 30% SQL)

**Algorithm:**
```python
# Step 1: Get follow relationships (SQL)
with Session(db_engine) as session:
    following_ids = session.query(Follow.follower_id)\
        .filter(Follow.user_id == agent_id)\
        .all()
    following_set = set(row[0] for row in following_ids)

# Step 2: Filter posts from Redis
recent_posts = redis.lrange("ysim:posts:recent", 0, limit*3)
follower_posts = []
other_posts = []

for post_id in recent_posts:
    post_data = redis.hgetall(f"ysim:post:{post_id}")
    author_id = post_data.get("user_id")
    
    if author_id in following_set:
        follower_posts.append(post_id)
    else:
        other_posts.append(post_id)

# Prioritize follower posts
follower_limit = int(limit * followers_ratio)  # e.g., 0.8 = 80%
recommendations = follower_posts[:follower_limit]
recommendations.extend(other_posts[:limit-len(recommendations)])
return recommendations
```

**Why Hybrid:**
- Follow relationships change frequently
- SQL JOIN more efficient for graph traversal
- Redis excels at post filtering and ranking

**Performance:** ~10-15ms (depends on follower count)
**Use Case:** Social media feeds, friend content

---

#### 5. Followers + Popularity (`rchrono_followers_popularity`)

**Redis Implementation:** 🔄 **Hybrid** (70% Redis, 30% SQL)

**Algorithm:**
```python
# Combines follower filtering with popularity ranking
following_set = get_following_from_sql(agent_id)
recent_posts = redis.lrange("ysim:posts:recent", 0, limit*5)

follower_posts = []
other_posts = []

for post_id in recent_posts:
    post_data = redis.hgetall(f"ysim:post:{post_id}")
    author_id = post_data.get("user_id")
    reaction_count = int(post_data.get("reaction_count", 0))
    
    post_info = {
        "id": post_id,
        "reactions": reaction_count,
        "is_follower": author_id in following_set
    }
    
    if post_info["is_follower"]:
        follower_posts.append(post_info)
    else:
        other_posts.append(post_info)

# Sort by time, then popularity
follower_posts_sorted = sorted(follower_posts, key=lambda x: -x["reactions"])
other_posts_sorted = sorted(other_posts, key=lambda x: -x["reactions"])

# Combine with ratio
return combine_with_ratio(follower_posts_sorted, other_posts_sorted, limit, ratio=0.8)
```

**Performance:** ~12-20ms
**Use Case:** Engagement-focused social feeds

---

#### 6. Comment Activity (`rchrono_comments`)

**Redis Implementation:** ✅ **100%**

**Algorithm:**
```python
# Prioritize posts with many comments
recent_posts = redis.lrange("ysim:posts:recent", 0, limit*5)
posts_with_comment_counts = []

for post_id in recent_posts:
    # Count comments (posts where comment_to == post_id)
    comment_count = 0
    for potential_comment_id in recent_posts:
        comment_data = redis.hgetall(f"ysim:post:{potential_comment_id}")
        if comment_data.get("comment_to") == post_id:
            comment_count += 1
    
    posts_with_comment_counts.append({
        "id": post_id,
        "comments": comment_count
    })

# Sort by comment activity
sorted_posts = sorted(posts_with_comment_counts, key=lambda x: -x["comments"])
return [p["id"] for p in sorted_posts[:limit]]
```

**Performance:** ~5-10ms (scales with post count)
**Use Case:** Discussion-heavy platforms, forums

---

#### 7. Common Interests (`common_interests`)

**Redis Implementation:** 🔄 **Hybrid** (Ready for full Redis, SQL fallback)

**Algorithm:**
```python
# Step 1: Get user interests (Redis when available)
user_interests_key = f"ysim:user:{agent_id}:interests"

if redis.exists(user_interests_key):
    # Full Redis path
    user_interests = redis.smembers(user_interests_key)
    recent_posts = redis.lrange("ysim:posts:recent", 0, limit*5)
    
    posts_with_scores = []
    for post_id in recent_posts:
        post_topics_key = f"ysim:post:{post_id}:topics"
        if redis.exists(post_topics_key):
            post_topics = redis.smembers(post_topics_key)
            # Set intersection for common topics
            common_count = len(user_interests & post_topics)
            if common_count > 0:
                posts_with_scores.append({
                    "id": post_id,
                    "score": common_count
                })
    
    sorted_posts = sorted(posts_with_scores, key=lambda x: -x["score"])
    return [p["id"] for p in sorted_posts[:limit]]
    
else:
    # SQL fallback
    return sql_query_common_interests(agent_id, limit)
```

**Redis Data Structures Required:**
- `ysim:user:{id}:interests` - Set of topic IDs
- `ysim:post:{id}:topics` - Set of topic IDs

**Performance:**
- Full Redis: ~3-5ms (set intersection)
- SQL fallback: ~50-100ms

**Current Status:** Redis-ready, graceful SQL fallback

---

#### 8. Similar Users (`similar_users_react`)

**Redis Implementation:** 🔄 **Hybrid** (demographics in SQL, reactions in Redis)

**Algorithm:**
```python
# Find users with similar demographics
similar_users = sql_query_similar_demographics(agent_id, fields=["age_group", "leaning"])
similar_user_ids = set(u["id"] for u in similar_users)

# Get posts they reacted to (Redis)
recent_posts = redis.lrange("ysim:posts:recent", 0, limit*3)
posts_with_scores = []

for post_id in recent_posts:
    reactions_key = f"ysim:post:{post_id}:reactions"
    if redis.exists(reactions_key):
        reactions = redis.smembers(reactions_key)
        # Count similar users who reacted
        similar_react_count = len(similar_user_ids & reactions)
        
        if similar_react_count > 0:
            posts_with_scores.append({
                "id": post_id,
                "score": similar_react_count
            })

sorted_posts = sorted(posts_with_scores, key=lambda x: -x["score"])
return [p["id"] for p in sorted_posts[:limit]]
```

**Redis Data Structures:**
- `ysim:post:{id}:reactions` - Set of user IDs who reacted

**Why Hybrid:**
- User demographics not always cached in Redis
- Demographics change infrequently, SQL is efficient
- Reaction data perfect for Redis sets

**Performance:** ~15-30ms

---

### Follow Recommendations

Follow recommendations use similar patterns but recommend users instead of posts.

#### 9. Popular Users

**Redis Implementation:** ✅ **100%**

```python
# Count followers for each user
all_user_ids = redis.smembers("ysim:user_mgmt:ids")
users_with_counts = []

for user_id in all_user_ids:
    if user_id == agent_id:
        continue
    
    followers_key = f"ysim:follow:{user_id}:followers"
    follower_count = redis.scard(followers_key)
    
    users_with_counts.append({
        "id": user_id,
        "followers": follower_count
    })

sorted_users = sorted(users_with_counts, key=lambda x: -x["followers"])
return [u["id"] for u in sorted_users[:limit]]
```

**Performance:** ~5-10ms for 1000 users

---

#### 10. Interest-Based Users

**Redis Implementation:** 🔄 **Hybrid**

```python
# Find users with similar interests
user_interests = redis.smembers(f"ysim:user:{agent_id}:interests")
all_user_ids = redis.smembers("ysim:user_mgmt:ids")

users_with_scores = []
for user_id in all_user_ids:
    if user_id == agent_id:
        continue
    
    other_interests = redis.smembers(f"ysim:user:{user_id}:interests")
    common_interests = len(user_interests & other_interests)
    
    if common_interests > 0:
        users_with_scores.append({
            "id": user_id,
            "score": common_interests
        })

sorted_users = sorted(users_with_scores, key=lambda x: -x["score"])
return [u["id"] for u in sorted_users[:limit]]
```

---

## Implementation Details

### File Structure

```
YSimulator/YServer/
├─ recsys/
│  ├─ content_recsys_redis.py  (677 lines - content algorithms)
│  └─ follow_recsys_redis.py   (398 lines - follow algorithms)
├─ recommendation/
│  ├─ content_recommender.py   (orchestration)
│  └─ follow_recommender.py    (orchestration)
└─ services/
   └─ recommendation_service.py (service layer)
```

### Key Functions

**content_recsys_redis.py:**
```python
def recommend_rchrono_redis(...)                     # Pure Redis
def recommend_rchrono_popularity_redis(...)          # Pure Redis
def recommend_rchrono_followers_redis(...)           # Hybrid
def recommend_rchrono_followers_popularity_redis(...) # Hybrid
def recommend_rchrono_comments_redis(...)            # Pure Redis
def recommend_common_interests_redis(...)            # Hybrid (ready)
def recommend_similar_users_react_redis(...)         # Hybrid
```

**follow_recsys_redis.py:**
```python
def recommend_popular_users_redis(...)               # Pure Redis
def recommend_interest_based_users_redis(...)        # Hybrid
```

---

## Performance Analysis

### Latency Benchmarks

| Mode | Redis Only | Hybrid | SQL Only |
|------|-----------|--------|----------|
| random | 0.8ms | - | 45ms |
| rchrono | 1.2ms | - | 50ms |
| rchrono_popularity | 2.5ms | - | 75ms |
| rchrono_followers | - | 12ms | 120ms |
| rchrono_comments | 5ms | - | 200ms |
| common_interests | 3ms* | 15ms | 180ms |

*When Redis data populated

### Scalability

**Redis Performance:**
- Handles 10K+ recommendations/sec
- Linear scaling with post count
- O(1) lookups for most operations

**Hybrid Performance:**
- Handles 500-1000 recommendations/sec
- Depends on SQL query complexity
- Benefits from SQL connection pooling

### Memory vs. Performance Trade-offs

| Approach | Memory | Speed | Complexity |
|----------|--------|-------|------------|
| Pure Redis | High | Fastest | Medium |
| Hybrid | Medium | Fast | High |
| Pure SQL | Low | Slowest | Low |

---

## Migration Path

### Phase 1: Current State ✅

- Pure Redis modes operational
- Hybrid modes with SQL fallback
- Graceful degradation

### Phase 2: Enhanced Redis (In Progress)

**Goals:**
- Populate interest caches automatically
- Pre-compute user similarity scores
- Cache demographic data in Redis

**Implementation:**
```python
# Auto-populate interests when posts created
def add_post_with_topics(post_data, topics):
    # Store post
    redis.hset(f"ysim:post:{post_id}", mapping=post_data)
    
    # Cache topics
    for topic in topics:
        redis.sadd(f"ysim:post:{post_id}:topics", topic)
    
    # Update user interests (learning)
    redis.sadd(f"ysim:user:{author_id}:interests", *topics)
```

### Phase 3: Full Redis (Future)

**Goals:**
- 95%+ Redis coverage
- Pre-computed recommendation caches
- Real-time updates via Redis Streams

**Architecture:**
```python
# Pre-computed recommendations
def update_recommendations_cache(user_id):
    recommendations = compute_all_modes(user_id)
    
    for mode, post_ids in recommendations.items():
        cache_key = f"ysim:recom:{user_id}:{mode}"
        redis.delete(cache_key)
        redis.lpush(cache_key, *post_ids)
        redis.expire(cache_key, 300)  # 5 min TTL
```

---

## Best Practices

### 1. Mode Selection

Choose recommendation mode based on use case:

- **High engagement:** `rchrono_popularity`
- **Social focus:** `rchrono_followers`
- **Content discovery:** `common_interests`
- **Discussion:** `rchrono_comments`
- **Exploration:** `random`

### 2. Caching Strategy

```python
# Cache recommendations
cache_key = f"recom:{agent_id}:{mode}"
cached = redis.get(cache_key)

if cached:
    return json.loads(cached)

recommendations = compute_recommendations(agent_id, mode)
redis.setex(cache_key, 60, json.dumps(recommendations))  # 1 min cache
return recommendations
```

### 3. Monitoring

Track key metrics:

```python
# Monitor recommendation performance
redis.incr(f"metrics:recom:{mode}:calls")
redis.hincrby(f"metrics:recom:{mode}:latency", "total_ms", latency)

# Alert on high latency
if latency > 100:
    logger.warning(f"Slow recommendation: {mode} took {latency}ms")
```

### 4. Fallback Strategy

Always implement graceful degradation:

```python
def get_recommendations_with_fallback(agent_id, mode, limit):
    try:
        # Try requested mode
        return recommend(agent_id, mode, limit)
    except RedisError:
        logger.warning(f"Redis error, falling back to rchrono")
        return recommend(agent_id, "rchrono", limit)
    except Exception as e:
        logger.error(f"Recommendation error: {e}")
        # Ultimate fallback: random
        return recommend(agent_id, "random", limit)
```

---

## Related Documentation

- [Redis Integration Guide](REDIS_INTEGRATION.md) - Setup and configuration
- [Redis Coverage Analysis](REDIS_COVERAGE_ANALYSIS.md) - Implementation status
- [Architecture Overview](../architecture/ARCHITECTURE.md) - System design

---

**Maintainer:** YSimulator Core Team  
**Version:** 3.0  
**Last Updated:** January 9, 2026
