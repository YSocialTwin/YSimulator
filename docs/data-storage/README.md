# Data Storage & Caching Documentation

This directory contains comprehensive documentation about YSimulator's hybrid database architecture, Redis caching integration, and data storage strategies.

## Overview

YSimulator implements a **hybrid storage architecture** that combines:
- **Relational Databases** (SQLite/PostgreSQL/MySQL) for persistent storage
- **Redis** (in-memory cache) for high-performance operations
- **Repository/Service Pattern** for clean separation of concerns

The system automatically detects Redis availability and gracefully falls back to SQL-only operations when Redis is unavailable.

## Documentation Files

### Core Architecture

- **[REDIS_INTEGRATION.md](REDIS_INTEGRATION.md)** - Complete Redis integration guide
  - Architecture overview and design patterns
  - Configuration and setup
  - Data structures and key naming conventions
  - Performance characteristics
  - Migration from SQL-only to hybrid mode

- **[REDIS_COVERAGE_ANALYSIS.md](REDIS_COVERAGE_ANALYSIS.md)** - Implementation status report
  - Method-by-method coverage analysis  
  - Service-level Redis support breakdown
  - Identified gaps and limitations
  - Performance benchmarks
  - Testing and validation

### Specialized Systems

- **[REDIS_RECOMMENDATION_SYSTEMS.md](REDIS_RECOMMENDATION_SYSTEMS.md)** - Recommendation engine caching
  - Content recommendation strategies
  - Follow recommendation algorithms
  - Redis data structures for recommendations
  - SQL vs Redis implementation differences
  - Performance optimization strategies

## Quick Reference

### Key Metrics (Current Status)

```
Redis Coverage: ~85-90% of operations
├─ User Management: 100% Redis-backed
├─ Posts & Content: 100% Redis-backed  
├─ Social Graph: 100% Redis-backed
├─ Recommendations: 60% Redis, 40% hybrid SQL+Redis
└─ Analytics: 30% Redis, 70% SQL-based
```

### When to Use Redis

✅ **Ideal for Redis:**
- User lookups and authentication
- Recent posts and timeline generation
- Social graph queries (followers, following)
- Reaction counts and engagement metrics
- Session and activity tracking

⚠️ **Hybrid (Redis + SQL):**
- Complex recommendations with interest matching
- Topic-based content filtering  
- User similarity calculations
- Demographic-based filtering

❌ **SQL-Only (By Design):**
- Historical analytics and aggregations
- Complex temporal queries
- Database initialization and migrations
- Administrative operations

### Configuration

Enable Redis in `server_config.json`:

```json
{
  "redis": {
    "enabled": true,
    "host": "localhost",
    "port": 6379,
    "db": 0,
    "decode_responses": false
  }
}
```

**Note:** `decode_responses: false` is required for binary data compatibility.

## Architecture Highlights

### Repository/Service Pattern

```
Client Request
     ↓
Server (OrchestratorServer)
     ↓
DatabaseServiceAdapter
     ↓
Service Layer (UserService, PostService, etc.)
     ↓
Repository Layer (RedisRepository, SQLRepository)
     ↓
Storage (Redis / PostgreSQL / MySQL / SQLite)
```

### Benefits

1. **Clean Separation**: Business logic in services, data access in repositories
2. **Easy Testing**: Mock repositories or services independently
3. **Flexible Backends**: Swap Redis/SQL implementations transparently
4. **Graceful Degradation**: Automatic fallback when Redis unavailable

### Key Design Decisions

- **No decode_responses**: Maintains binary compatibility, requires manual decoding
- **Hybrid Approach**: Redis for speed, SQL for complex queries
- **Index Management**: Username, topic, and relationship indices in Redis
- **TTL Strategy**: Optional expiration for transient data
- **Batch Operations**: Efficient multi-record operations in both backends

## Getting Started

1. **Read** [REDIS_INTEGRATION.md](REDIS_INTEGRATION.md) for setup and configuration
2. **Review** [REDIS_COVERAGE_ANALYSIS.md](REDIS_COVERAGE_ANALYSIS.md) to understand what's supported
3. **Explore** [REDIS_RECOMMENDATION_SYSTEMS.md](REDIS_RECOMMENDATION_SYSTEMS.md) for recommendation details

## Common Tasks

### Check Redis Status

```python
from YSimulator.YServer.server import OrchestratorServer

server = OrchestratorServer(config)
if server.use_redis:
    print("Redis is enabled and connected")
else:
    print("Running in SQL-only mode")
```

### Monitor Redis Memory

```bash
redis-cli INFO memory
redis-cli --bigkeys
```

### Performance Tuning

See [REDIS_INTEGRATION.md#Performance](REDIS_INTEGRATION.md#performance-optimization) for:
- Memory optimization strategies
- Key expiration policies
- Batch operation patterns
- Connection pooling configuration

## Migration Notes

If migrating from SQL-only to Redis-enabled:

1. No code changes required in application logic
2. Redis structures populate automatically during operation
3. Gradual transition as cache warms up
4. Monitor memory usage during initial population
5. See [REDIS_INTEGRATION.md#Migration](REDIS_INTEGRATION.md#migration-guide)

## Contributing

When adding new features:

1. Implement in both Redis and SQL repositories if applicable
2. Add tests for both backends
3. Update coverage analysis documentation
4. Document any new Redis data structures
5. Consider memory implications for large-scale deployments

## Related Documentation

- [Architecture Overview](../architecture/ARCHITECTURE.md) - System design
- [Configuration Guide](../configuration/CONFIG.md) - Server configuration
- [Testing Guide](../testing/TESTING.md) - Running tests
- [Performance Tuning](../operations/PERFORMANCE.md) - Optimization strategies

---

**Last Updated:** January 9, 2026  
**Version:** 3.0 (Complete rewrite based on current codebase)  
**Maintainer:** YSimulator Core Team
