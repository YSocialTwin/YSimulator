# YServer Repository Pattern Implementation

## Overview

This document describes the Repository Pattern implementation for YServer, which provides a clean separation between data access logic and business logic.

## Architecture

The refactored YServer follows a layered architecture:

```
┌─────────────────────────────────────┐
│        Service Layer                │
│  (Business Logic Coordination)     │
│                                     │
│  ▪ UserService                      │
│  ▪ PostService                      │
│  ▪ RecommendationService            │
└───────────────┬─────────────────────┘
                │
                ▼
┌─────────────────────────────────────┐
│       Repository Layer              │
│   (Data Access Abstraction)         │
│                                     │
│  ▪ UserRepository                   │
│  ▪ PostRepository                   │
│  ▪ FollowRepository                 │
│  ▪ InterestRepository               │
│  ▪ RecommendationRepository         │
└───────────────┬─────────────────────┘
                │
        ┌───────┴────────┐
        ▼                ▼
┌──────────────┐  ┌──────────────┐
│ SQL Backend  │  │ Redis Backend│
│ (SQLAlchemy) │  │  (Cache)     │
└──────────────┘  └──────────────┘
```

## Components

### 1. Repository Layer (`YSimulator/YServer/repositories/`)

The repository layer provides abstract interfaces and concrete implementations for data access operations.

#### Abstract Interfaces (`base_repository.py`)

Defines the contract that all repository implementations must follow:

- **BaseRepository**: Common operations (health checks)
- **UserRepository**: User management operations
- **PostRepository**: Post and interaction operations
- **FollowRepository**: Follow relationship operations
- **InterestRepository**: Interest/topic operations
- **RecommendationRepository**: Recommendation and round operations
- **ArticleRepository**: Article/website operations
- **ImageRepository**: Image operations

#### SQL Implementation (`sql_repository.py`)

Concrete implementations using SQLAlchemy for SQL databases:

- **SQLUserRepository**: User operations with SQLAlchemy
- **SQLPostRepository**: Post operations with SQLAlchemy
- **SQLFollowRepository**: Follow relationship operations with SQLAlchemy
- **SQLInterestRepository**: Interest/topic operations with SQLAlchemy
- **SQLRecommendationRepository**: Recommendation operations with SQLAlchemy

Key features:
- Automatic field name mapping (e.g., `tweet` ↔ `text`, `user_id` ↔ `author`)
- Transaction management with proper session cleanup
- Error handling and logging

#### Redis Implementation (`redis_repository.py`)

Concrete implementations using Redis for high-performance caching:

- **RedisUserRepository**: User operations with Redis
- **RedisPostRepository**: Post operations with Redis
- **RedisFollowRepository**: Follow relationship operations with Redis
- **RedisInterestRepository**: Interest/topic operations with Redis
- **RedisRecommendationRepository**: Recommendation operations with Redis

Key features:
- Hash-based storage for complex objects
- Set-based storage for relationships
- Sorted set-based storage for time-series data
- Automatic byte string encoding/decoding

### 2. Service Layer (`YSimulator/YServer/services/`)

The service layer implements business logic and coordinates between multiple repositories.

#### UserService (`user_service.py`)

Manages user-related business operations:

- User registration (single and batch)
- User retrieval and updates
- User interests tracking
- User archetype management

Example usage:
```python
from YSimulator.YServer.services import UserService
from YSimulator.YServer.repositories import SQLUserRepository

# Initialize
user_repo = SQLUserRepository(engine, logger)
user_service = UserService(user_repo)

# Register a user
user_data = {"id": "user1", "username": "john", "leaning": "0.5"}
success = user_service.register_user(user_data)

# Get a user
user = user_service.get_user("user1")
```

#### PostService (`post_service.py`)

Manages post-related business operations:

- Post creation and retrieval
- Thread context management
- Reactions and interactions
- Topic associations
- Post search by topic

Example usage:
```python
from YSimulator.YServer.services import PostService
from YSimulator.YServer.repositories import SQLPostRepository

# Initialize
post_repo = SQLPostRepository(engine, logger)
post_service = PostService(post_repo)

# Create a post
post_data = {
    "id": "post1",
    "author": "user1",
    "text": "Hello, world!",
    "round": "round1"
}
post_id = post_service.create_post(post_data)

# Add a reaction
reaction_data = {
    "id": "reaction1",
    "post_id": post_id,
    "user_id": "user2"
}
post_service.add_reaction(reaction_data)
```

#### RecommendationService (`recommendation_service.py`)

Manages recommendation-related business operations:

- Round management
- Follow relationships (single and batch)
- Agent opinions on topics
- Data cleanup and consolidation

Example usage:
```python
from YSimulator.YServer.services import RecommendationService
from YSimulator.YServer.repositories import (
    SQLRecommendationRepository,
    SQLFollowRepository
)

# Initialize
rec_repo = SQLRecommendationRepository(engine, logger)
follow_repo = SQLFollowRepository(engine, logger)
rec_service = RecommendationService(rec_repo, follow_repository=follow_repo)

# Create a round
round_id = rec_service.get_or_create_round(day=1, hour=10)

# Add a follow relationship
rec_service.add_follow_relationship("user1", "user2")
```

## Benefits

### 1. Separation of Concerns

- **Repositories**: Handle only data access and storage
- **Services**: Handle only business logic and coordination
- **Models**: Handle only data structure

### 2. Multiple Storage Backends

The same service can work with different storage backends:

```python
# Use SQL backend
user_repo = SQLUserRepository(engine, logger)
user_service = UserService(user_repo)

# Or use Redis backend
user_repo = RedisUserRepository(redis_client, logger=logger)
user_service = UserService(user_repo)
```

### 3. Testability

Repositories can be easily mocked for testing:

```python
from unittest.mock import Mock

# Mock repository for testing
mock_repo = Mock(spec=UserRepository)
mock_repo.get_user.return_value = {"id": "user1", "username": "test"}

# Test service with mock
service = UserService(mock_repo)
user = service.get_user("user1")
```

### 4. Maintainability

- **Localized Changes**: Changes to data access logic don't affect business logic
- **Clear Interfaces**: Abstract interfaces make it clear what operations are available
- **Documentation**: Type hints and docstrings document expected behavior

### 5. Extensibility

New storage backends can be added by implementing the repository interfaces:

```python
class MongoDBUserRepository(UserRepository):
    """MongoDB implementation of UserRepository."""
    
    def __init__(self, mongo_client, logger=None):
        self.client = mongo_client
        self.logger = logger or logging.getLogger(__name__)
    
    def register_user(self, user_data: Dict[str, Any]) -> bool:
        # Implementation using MongoDB
        pass
```

## Migration Guide

### For New Code

Use the new repository and service pattern:

```python
# 1. Initialize repositories
user_repo = SQLUserRepository(engine, logger)
post_repo = SQLPostRepository(engine, logger)

# 2. Initialize services
user_service = UserService(user_repo)
post_service = PostService(post_repo)

# 3. Use services for business operations
user_service.register_user(user_data)
post_service.create_post(post_data)
```

### For Existing Code

The existing `db_middleware.py` continues to work and is not affected by these changes. You can gradually migrate code to use the new pattern:

**Before:**
```python
from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware

middleware = DatabaseMiddleware(db_config, redis_config)
middleware.register_user(user_data)
```

**After:**
```python
from YSimulator.YServer.services import UserService
from YSimulator.YServer.repositories import SQLUserRepository

user_repo = SQLUserRepository(engine, logger)
user_service = UserService(user_repo)
user_service.register_user(user_data)
```

## Testing

### Repository Tests

Test repository implementations with mocked database connections:

```bash
pytest YSimulator/tests/test_repositories.py -v
```

### Service Tests

Test service business logic with mocked repositories:

```bash
pytest YSimulator/tests/test_services.py -v
```

### All Tests

Run all tests including the new repository and service tests:

```bash
pytest YSimulator/tests/ -v
```

## Field Name Mappings

The repository layer handles translation between different naming conventions:

| API Field Name | Database Model Field | Description |
|----------------|---------------------|-------------|
| `text` | `tweet` | Post content |
| `author` | `user_id` | Post author ID |
| `parent_post` | `comment_to` | Parent post ID (for replies) |
| `root_post` | `thread_id` | Root post ID (for threads) |
| `num_reactions` | `reaction_count` | Number of reactions |
| `followee_id` | `user_id` | User being followed |
| `round_id` | `tid` | Transaction/round ID (in Agent_Opinion) |

## Best Practices

1. **Use Services for Business Logic**: Never directly call repositories from application code; always go through services.

2. **Handle Errors Gracefully**: Services catch repository exceptions and return appropriate values (None, False, empty lists).

3. **Use Type Hints**: All methods include type hints for better IDE support and documentation.

4. **Log Operations**: Both repositories and services log errors with context for debugging.

5. **Test with Mocks**: Use mocked repositories when testing services to isolate business logic.

6. **Close Sessions**: Repositories automatically close database sessions in finally blocks.

## Future Enhancements

Potential improvements for the repository pattern:

1. **Query Objects**: Implement query builder objects for complex queries
2. **Unit of Work**: Implement transaction management across multiple repositories
3. **Caching Layer**: Add automatic caching between service and repository layers
4. **Event System**: Add event hooks for operations (before_save, after_save, etc.)
5. **Audit Logging**: Track all data modifications through repositories

## References

- [Repository Pattern (Martin Fowler)](https://martinfowler.com/eaaCatalog/repository.html)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Redis Documentation](https://redis.io/documentation)
- [CODEBASE_ANALYSIS.md](../development/CODEBASE_ANALYSIS.md) - Original refactoring proposal
