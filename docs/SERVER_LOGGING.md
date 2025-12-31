# YServer Request Logging

## Overview

The YServer (OrchestratorServer) now logs all incoming requests to a `_server.log` file located in the logs directory. This provides comprehensive tracking of all client interactions with the server.

## Log Format

Each log entry is a single-line JSON object with the following fields:

```json
{
  "request_id": "1767202193.4879587-5450092108",
  "client_name": "client_1",
  "path": "register_client",
  "status_code": 200,
  "duration": 0.000128,
  "time": "2025-12-31T17:29:53.488107+00:00",
  "tid": "f87e903f-4d67-4792-9f34-d34e08904628",
  "day": 1,
  "hour": 1
}
```

### Field Descriptions

- **request_id**: Unique identifier for the request (format: `timestamp-random_number`)
- **client_name**: The client or agent that made the request
- **path**: The method name that was called (e.g., `register_client`, `submit_actions`)
- **status_code**: HTTP-style status code (200 for success, 500 for errors)
- **duration**: Execution time in seconds (float)
- **time**: ISO 8601 timestamp of when the request completed
- **tid**: Current simulation round ID (UUID)
- **day**: Current simulation day number
- **hour**: Current simulation hour/slot number
- **error** (optional): Error message if status_code is 500

## Log File Location

The server request log is saved to:
```
<config_path>/logs/_server.log
```

This is a fixed filename that all server instances write to, making it easy to locate and parse server request logs.

## Logged Methods

The following server methods are logged:

### Client Lifecycle
- `register_client` - Client registration
- `deregister_client` - Client deregistration
- `complete_client` - Client completion
- `heartbeat` - Client heartbeat/keepalive
- `get_instruction` - Get next simulation instruction

### Agent Operations
- `register_agents` - Batch agent registration
- `submit_actions` - Submit agent actions for a slot

### Data Retrieval
- `get_post` - Get post by ID
- `get_user` - Get user by ID
- `get_thread_context` - Get thread context for a post
- `get_unreplied_mentions` - Get unreplied mentions for a user

### Recommendations
- `get_recommended_posts` - Get content recommendations
- `get_follow_suggestions` - Get follow suggestions

### Social Network
- `add_follow_relationship` - Add single follow relationship
- `add_follow_relationships_batch` - Batch add follow relationships

### Search
- `search_posts_by_topic` - Search posts by topic

## Usage Example

When running the server, the log file is automatically created:

```python
# Server is started with run_server.py
python run_server.py --config ./example/demo_small

# Logs are written to:
# ./example/demo_small/logs/_server.log
```

## Parsing Logs

You can easily parse and analyze the logs using Python:

```python
import json

# Read and parse log entries
with open('logs/_server.log', 'r') as f:
    for line in f:
        entry = json.loads(line.strip())
        print(f"[{entry['time']}] {entry['client_name']} -> {entry['path']} "
              f"({entry['status_code']}) {entry['duration']:.4f}s")
```

## Performance Considerations

- Log files use rotating file handlers (10MB per file, 5 backups)
- Logging is asynchronous and should not significantly impact server performance
- Failed logging attempts do not break the server (errors are silently caught)
- Each request generates exactly one log entry

## Monitoring and Analysis

The server logs can be used for:

1. **Performance Analysis**: Track request durations to identify bottlenecks
2. **Usage Patterns**: Analyze which methods are called most frequently
3. **Error Tracking**: Identify failed requests (status_code: 500)
4. **Simulation Progress**: Monitor day/hour progression
5. **Client Behavior**: Track which clients are making requests
6. **Debugging**: Correlate client issues with server-side logs
