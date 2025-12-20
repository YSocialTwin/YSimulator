# Recommendation System: Redis vs SQLAlchemy Implementation Comparison

## Overview

The YSimulator recommendation system supports 10 different recommendation modes. Due to architectural differences between Redis (key-value store) and SQL databases (relational), not all modes are fully supported in Redis. This document details the implementation differences and expected behavior variations.

## Summary Table

| Mode | Redis Support | SQL Support | Notes |
|------|---------------|-------------|-------|
| `random` | ✅ Full | ✅ Full | Identical behavior |
| `rchrono` | ✅ Full | ✅ Full | Minor differences (see below) |
| `rchrono_popularity` | ⚠️ Partial | ✅ Full | Different sorting approach |
| `rchrono_followers` | ❌ Fallback | ✅ Full | Falls back to `rchrono` |
| `rchrono_followers_popularity` | ❌ Fallback | ✅ Full | Falls back to `rchrono` |
| `rchrono_comments` | ❌ Fallback | ✅ Full | Falls back to `rchrono` |
| `common_interests` | ❌ Fallback | ✅ Full | Falls back to `rchrono` |
| `common_user_interests` | ❌ Fallback | ✅ Full | Falls back to `rchrono` |
| `similar_users_react` | ❌ Fallback | ✅ Full | Falls back to `rchrono` |
| `similar_users_posts` | ❌ Fallback | ✅ Full | Falls back to `rchrono` |

**Legend:**
- ✅ Full: Mode is fully supported with expected behavior
- ⚠️ Partial: Mode is supported but with behavioral differences
- ❌ Fallback: Mode falls back to `rchrono` with logging

---

## Detailed Mode Comparison

### 1. `random` - Random Post Ordering

#### SQL Implementation
```sql
SELECT p.id FROM post p
INNER JOIN rounds rd ON p.round = rd.id
WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
    AND p.user_id != :agent_id
ORDER BY RANDOM()
LIMIT :limit
```

**Behavior:**
- Filters posts by visibility window (day/hour threshold)
- Excludes agent's own posts
- Returns random selection from all visible posts
- Visibility window precisely controlled by `visibility_rounds` parameter

#### Redis Implementation
```python
# Get recent posts (limited to last 50)
valid_posts = [p for p in recent_posts if p.user_id != agent_id]
post_ids = random.sample(valid_posts, limit)
```

**Behavior:**
- Uses Redis `ysim:posts:recent` list (limited to last 50 posts)
- Excludes agent's own posts
- Returns random selection from recent posts
- **No visibility window filtering** (already limited by Redis list size)

#### Key Differences
| Aspect | SQL | Redis |
|--------|-----|-------|
| Visibility filtering | ✅ Precise (day/hour) | ❌ Fixed (last 50 posts) |
| Post pool size | Based on `visibility_rounds` | Fixed (50 posts max) |
| Randomness | Database RANDOM() | Python random.sample() |

#### Example Results

**Scenario:** Agent requests 5 random posts with `visibility_rounds=36`

**SQL Results:**
```
Post IDs: ['post-123', 'post-456', 'post-789', 'post-234', 'post-567']
Source: All posts from last 36 time slots (could be 100+ posts)
Distribution: Truly random across entire visibility window
```

**Redis Results:**
```
Post IDs: ['post-901', 'post-123', 'post-456', 'post-345', 'post-678']
Source: Last 50 posts stored in Redis
Distribution: Random from recent 50 posts only
```

**Impact:** Redis may have selection bias toward very recent posts if there are many posts in the visibility window.

---

### 2. `rchrono` - Reverse Chronological Ordering

#### SQL Implementation
```sql
SELECT p.id FROM post p
INNER JOIN rounds rd ON p.round = rd.id
WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
    AND p.user_id != :agent_id
ORDER BY rd.day DESC, rd.hour DESC
LIMIT :limit
```

**Behavior:**
- Orders by round day/hour descending (newest first)
- Precise visibility window filtering
- Returns exact N newest posts within visibility window

#### Redis Implementation
```python
# Recent list is already in reverse chronological order
valid_posts = [p for p in recent_posts if p.user_id != agent_id]
post_ids = valid_posts[:limit]
```

**Behavior:**
- Redis `ysim:posts:recent` list is maintained in reverse chronological order
- Takes first N posts after filtering
- Already limited to last 50 posts

#### Key Differences
| Aspect | SQL | Redis |
|--------|-----|-------|
| Ordering precision | ✅ Day+Hour granularity | ✅ Insertion order |
| Visibility filtering | ✅ Configurable window | ❌ Fixed (50 posts) |
| Performance | Database sort | O(1) list slice |

#### Example Results

**Scenario:** Agent requests 5 posts in reverse chronological order

**SQL Results:**
```
Posts: [
  {id: 'post-999', day: 5, hour: 12},  # Most recent
  {id: 'post-998', day: 5, hour: 11},
  {id: 'post-997', day: 5, hour: 11},
  {id: 'post-996', day: 5, hour: 10},
  {id: 'post-995', day: 5, hour: 9}
]
```

**Redis Results:**
```
Posts: [
  {id: 'post-999'},  # Most recent in Redis list
  {id: 'post-998'},
  {id: 'post-997'},
  {id: 'post-996'},
  {id: 'post-995'}
]
```

**Impact:** Results are nearly identical for recent posts. SQL has more precise control over visibility window.

---

### 3. `rchrono_popularity` - Chronological with Popularity Boost

#### SQL Implementation
```sql
SELECT p.id 
FROM post p
INNER JOIN rounds rd ON p.round = rd.id
LEFT JOIN (
    SELECT post_id, COUNT(*) as reaction_count
    FROM reactions
    GROUP BY post_id
) r ON p.id = r.post_id
WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
    AND p.user_id != :agent_id
ORDER BY rd.day DESC, rd.hour DESC, COALESCE(r.reaction_count, 0) DESC
LIMIT :limit
```

**Behavior:**
- Aggregates reaction counts via JOIN
- Orders by day/hour first, then by reaction count
- Prioritizes popular posts within same time slot

#### Redis Implementation
```python
valid_posts = [
    {
        'id': post_id,
        'reaction_count': int(post_data.get('reaction_count', 0))
    }
    for post in recent_posts if post.user_id != agent_id
]
sorted_posts = sorted(valid_posts, key=lambda x: x['reaction_count'], reverse=True)
post_ids = [p['id'] for p in sorted_posts[:limit]]
```

**Behavior:**
- Uses cached `reaction_count` field in post hash
- Sorts ONLY by reaction count (not by time first)
- No visibility window filtering

#### Key Differences
| Aspect | SQL | Redis |
|--------|-----|-------|
| Primary sort | Time (day/hour) | Popularity only |
| Secondary sort | Popularity | None |
| Reaction counting | JOIN aggregation | Cached field |
| Visibility filtering | ✅ Configurable | ❌ Fixed (50 posts) |

#### Example Results

**Scenario:** Agent requests 5 posts with popularity boost

**SQL Results:**
```
Posts: [
  {id: 'post-999', day: 5, hour: 12, reactions: 5},  # Recent + popular
  {id: 'post-998', day: 5, hour: 12, reactions: 3},  # Recent
  {id: 'post-997', day: 5, hour: 11, reactions: 8},  # Slightly older but popular
  {id: 'post-996', day: 5, hour: 11, reactions: 2},
  {id: 'post-995', day: 5, hour: 10, reactions: 1}
]
Time-first ordering: Posts from hour 12 appear before hour 11
```

**Redis Results:**
```
Posts: [
  {id: 'post-850', reactions: 15},  # Most popular (could be older)
  {id: 'post-997', reactions: 8},
  {id: 'post-999', reactions: 5},
  {id: 'post-998', reactions: 3},
  {id: 'post-700', reactions: 2}   # Old but has reactions
]
Popularity-only ordering: May include older posts with many reactions
```

**Impact:** **SIGNIFICANT DIFFERENCE**. SQL prioritizes recent posts with popularity as tiebreaker. Redis prioritizes popularity regardless of age, potentially showing older viral posts.

---

### 4-10. Complex Modes (Followers, Interests, Similar Users)

These modes require complex SQL JOINs with multiple tables:
- `rchrono_followers`: JOINs with `follow` table
- `rchrono_followers_popularity`: JOINs with `follow` and `reactions` tables
- `rchrono_comments`: Aggregates comment counts via self-JOIN
- `common_interests`: JOINs with `post_topics` and `user_interest` tables
- `common_user_interests`: Multi-table JOINs with user interests and reactions
- `similar_users_react`: JOINs with `user_mgmt` for demographics matching
- `similar_users_posts`: JOINs with `user_mgmt` for demographics matching

#### SQL Implementation
Each mode has a specialized query with appropriate JOINs. See server.py for full SQL queries.

**Example (`rchrono_followers`):**
```sql
SELECT DISTINCT p.id 
FROM post p
INNER JOIN rounds rd ON p.round = rd.id
INNER JOIN follow f ON p.user_id = f.follower_id
WHERE f.user_id = :agent_id 
    AND f.action = 'follow'
    AND (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
    AND p.user_id != :agent_id
ORDER BY rd.day DESC, rd.hour DESC
LIMIT :limit
```

#### Redis Implementation
```python
# All complex modes fall back to reverse chronological
if mode in ["rchrono_followers", "rchrono_followers_popularity", ...]:
    logger.info(f"Mode {mode} not fully supported in Redis, using rchrono fallback")
    post_ids = [p['id'] for p in valid_posts_with_data[:limit]]
```

**Behavior:**
- Logs warning about fallback
- Returns posts in reverse chronological order
- **Ignores** all special filtering (followers, interests, demographics)

#### Key Differences
| Aspect | SQL | Redis |
|--------|-----|-------|
| Special filtering | ✅ Full support | ❌ Not supported |
| Behavior | Mode-specific | Generic rchrono |
| User notice | None | Logged warning |

#### Example Results

**Scenario:** Agent requests posts from followed users (`rchrono_followers`)

**SQL Results:**
```
Posts from followed users only:
- post-123 (from user-456, follower)
- post-124 (from user-789, follower)
- post-125 (from user-456, follower)
- post-126 (from user-234, follower)
- post-127 (from user-789, follower)

All posts are from users the agent follows
```

**Redis Results:**
```
Recent posts (may or may not be from followers):
- post-999 (from user-111, NOT a follower)
- post-998 (from user-456, follower)
- post-997 (from user-222, NOT a follower)
- post-996 (from user-789, follower)
- post-995 (from user-333, NOT a follower)

WARNING: Mode rchrono_followers not fully supported in Redis, using rchrono fallback
```

**Impact:** **CRITICAL DIFFERENCE**. Redis ignores all personalization and returns generic recent posts.

---

## Architectural Limitations

### Why Redis Doesn't Support Complex Modes

1. **No Relational Joins**: Redis is a key-value store without native JOIN operations
2. **Data Denormalization**: Redis stores posts as individual hashes without relationships
3. **Limited Querying**: Redis doesn't support complex WHERE clauses or aggregations
4. **Performance Trade-off**: Redis is optimized for fast key-value access, not complex queries

### Redis Data Structure
```
ysim:posts:recent -> List of post IDs (FIFO, max 50)
ysim:posts:{post_id} -> Hash with post data
  - id: UUID
  - user_id: UUID
  - tweet: text
  - round: UUID
  - reaction_count: integer (cached)
  - thread_id: UUID
  - comment_to: UUID or -1
  - shared_from: UUID or -1
  - news_id: integer or -1
```

**Missing in Redis:**
- Follow relationships
- Post topics
- User interests
- User demographics
- Comment threading beyond IDs
- Historical reaction details

---

## Recommendations for Production Use

### When to Use Redis
✅ **Good for:**
- High-performance scenarios requiring low latency
- Simple recommendation modes (`random`, `rchrono`)
- Prototype/development environments
- Scenarios where recent posts (last 50) are sufficient

❌ **Not suitable for:**
- Personalized recommendations (followers, interests)
- Content-based filtering (topics, similar users)
- Popularity-based recommendations requiring historical data
- Production systems requiring full feature parity

### Alignment Strategy

To maximize behavioral alignment between Redis and SQL:

1. **Use SQL for Production**: When full functionality is needed
2. **Limit Redis to Simple Modes**: Explicitly configure only `random` or `rchrono` when using Redis
3. **Monitor Fallbacks**: Check logs for fallback warnings
4. **Increase Redis Cache**: Consider increasing Redis `ysim:posts:recent` list size from 50 to match typical visibility window
5. **Add Relationship Caching**: Future improvement could cache follower lists and user interests in Redis

### Configuration Example

```json
{
  "database": {
    "type": "sqlite"
  },
  "redis": {
    "enabled": false,  // Disable for personalized recommendations
    "host": "localhost",
    "port": 6379
  },
  "agents": {
    "recsys": {
      "mode": "rchrono_followers",  // Requires SQL
      "n_posts": 5,
      "visibility_rounds": 36
    }
  }
}
```

**For Redis-only deployments:**
```json
{
  "redis": {
    "enabled": true,
    "sliding_window_days": 2
  },
  "agents": {
    "recsys": {
      "mode": "rchrono",  // Use simple mode compatible with Redis
      "n_posts": 5
    }
  }
}
```

---

## Future Improvements

To achieve better parity between Redis and SQL:

1. **Cache Relationship Data**:
   ```
   ysim:user:{user_id}:follows -> Set of followed user IDs
   ysim:user:{user_id}:interests -> Set of interest IDs
   ```

2. **Enhanced Post Metadata**:
   ```
   ysim:posts:{post_id} -> Add fields:
     - follower_count
     - comment_count
     - topic_ids (list)
   ```

3. **Implement Redis-based Filtering**:
   - Check follower relationships using cached sets
   - Filter by topics using set intersections
   - Approximate popularity ranking using cached counts

4. **Hybrid Approach**:
   - Use Redis for initial fast filtering (last 100 posts)
   - Fall back to SQL for complex queries if Redis doesn't have enough data

---

## Testing Scenarios

### Test Case 1: Basic Functionality
```python
# Both should work
redis_posts = server.get_recommended_posts(agent_id, mode="random", limit=5)
sql_posts = server.get_recommended_posts(agent_id, mode="random", limit=5)

assert len(redis_posts) == 5
assert len(sql_posts) == 5
# Note: Actual post IDs will differ due to selection pool differences
```

### Test Case 2: Fallback Behavior
```python
# Redis should log warning and fallback
redis_posts = server.get_recommended_posts(agent_id, mode="rchrono_followers", limit=5)
# Check logs for: "Mode rchrono_followers not fully supported in Redis, using rchrono fallback"

# SQL should work without warnings
sql_posts = server.get_recommended_posts(agent_id, mode="rchrono_followers", limit=5)
```

### Test Case 3: Popularity Sorting
```python
# SQL: time-first, popularity-second
sql_posts = server.get_recommended_posts(agent_id, mode="rchrono_popularity", limit=5)

# Redis: popularity-only
redis_posts = server.get_recommended_posts(agent_id, mode="rchrono_popularity", limit=5)

# Results will differ significantly
# SQL posts: recent posts sorted by reactions
# Redis posts: most reacted posts (regardless of age)
```

---

## Conclusion

The YSimulator recommendation system provides comprehensive functionality through SQL databases, with Redis offering a performance-optimized subset of features. For production deployments requiring personalized recommendations, **SQL databases are strongly recommended**. Redis should be used for development, testing, or high-performance scenarios where simple recent-post recommendations are sufficient.

Key takeaway: **Redis trades functionality for performance**, providing 3 full modes (random, rchrono, rchrono_popularity with caveats) out of 10 total modes.
