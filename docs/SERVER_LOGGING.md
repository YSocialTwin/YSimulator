# YServer Request Logging

## Overview

The YServer (OrchestratorServer) logs all incoming requests to provide comprehensive tracking of client interactions with simulation state context. This enables performance analysis, debugging, and usage pattern monitoring.

### What Gets Logged

Every server method call is logged with:
- **Request identification** - Unique IDs for tracing
- **Client information** - Which client made the request
- **Timing data** - Execution duration
- **Simulation context** - Current day, hour, and round
- **Status information** - Success or failure

### Log File Location

Server request logs are saved to:
```
<config_path>/logs/_server.log
```

This is a fixed filename that all server instances write to, making it easy to locate and parse.

---

## Log Entry Format

Each log entry is a single-line JSON object:

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

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | string | Unique identifier for this request (format: `timestamp-uuid`) |
| `client_name` | string | Client ID that made the request ("unknown" if not provided) |
| `path` | string | Method name that was called (e.g., `register_client`) |
| `status_code` | number | HTTP-style status code (200 = success, 500 = error) |
| `duration` | number | Execution time in seconds (float) |
| `time` | string | ISO 8601 timestamp when request completed |
| `tid` | string | Current simulation round ID (UUID) |
| `day` | number | Current simulation day number |
| `hour` | number | Current simulation hour/slot number |
| `error` | string | Error message (only present if status_code is 500) |

### Request ID Format

Request IDs follow the pattern: `{timestamp}-{uuid_suffix}`

- **timestamp**: Unix timestamp with microseconds (e.g., `1767202193.4879587`)
- **uuid_suffix**: Last 10 characters of a UUID (e.g., `5450092108`)
- **Uniqueness**: Guaranteed unique across all requests
- **Sortability**: Chronologically sortable by timestamp prefix

---

## Logged Methods

The following 16 server methods are automatically logged:

### Client Lifecycle

| Method | Purpose |
|--------|---------|
| `register_client` | Client registration at simulation start |
| `deregister_client` | Client deregistration at simulation end |
| `complete_client` | Client completion notification |
| `heartbeat` | Client heartbeat/keepalive signal |
| `get_instruction` | Get next simulation instruction |

### Agent Operations

| Method | Purpose |
|--------|---------|
| `register_agents` | Batch agent registration |
| `submit_actions` | Submit agent actions for a time slot |

### Data Retrieval

| Method | Purpose |
|--------|---------|
| `get_post` | Retrieve post by ID |
| `get_user` | Retrieve user by ID |
| `get_thread_context` | Get comment thread context for a post |
| `get_unreplied_mentions` | Get unreplied mentions for a user |

### Recommendations

| Method | Purpose |
|--------|---------|
| `get_recommended_posts` | Get content recommendations for user |
| `get_follow_suggestions` | Get follow suggestions for user |

### Social Network

| Method | Purpose |
|--------|---------|
| `add_follow_relationship` | Add single follow relationship |
| `add_follow_relationships_batch` | Batch add follow relationships |

### Search

| Method | Purpose |
|--------|---------|
| `search_posts_by_topic` | Search posts by topic keywords |

---

## Client Identification

All server methods now accept an optional `client_id` parameter to identify the requesting client.

### How It Works

1. Client passes `client_id` when calling server methods
2. Server's logging decorator extracts `client_id` from method parameters
3. `client_name` field in log is set to the client_id value
4. If no `client_id` parameter provided, logs show "unknown"

### Implementation

The logging decorator uses `inspect.signature()` to check if a method has a parameter named `client_id`:

```python
@log_server_request
def get_post(self, post_id: str, client_id: str = None):
    # client_id is automatically logged
    ...
```

### Why Some Methods Show "Unknown"

Methods without a `client_id` parameter will show "unknown" in logs. This is expected for:
- Administrative methods that don't relate to specific clients
- Internal server operations

---

## Usage Examples

### Running the Server

When running the server, the log file is automatically created:

```bash
python run_server.py --config ./example/rule_population_100

# Logs written to:
# ./example/rule_population_100/logs/_server.log
```

### Parsing Logs with Python

```python
import json

# Read and parse log entries
with open('logs/_server.log', 'r') as f:
    for line in f:
        entry = json.loads(line.strip())
        print(f"[{entry['time']}] {entry['client_name']} -> {entry['path']} "
              f"({entry['status_code']}) {entry['duration']:.4f}s")
```

### Analyzing Performance

```python
import json
from collections import defaultdict

# Calculate average duration per method
method_times = defaultdict(list)

with open('logs/_server.log', 'r') as f:
    for line in f:
        entry = json.loads(line.strip())
        method_times[entry['path']].append(entry['duration'])

# Print averages
for method, times in sorted(method_times.items()):
    avg = sum(times) / len(times)
    print(f"{method}: {avg:.4f}s (n={len(times)})")
```

### Finding Errors

```python
import json

# Find all failed requests
with open('logs/_server.log', 'r') as f:
    for line in f:
        entry = json.loads(line.strip())
        if entry['status_code'] == 500:
            print(f"ERROR in {entry['path']}: {entry.get('error', 'Unknown')}")
            print(f"  Client: {entry['client_name']}, Time: {entry['time']}")
```

### Tracking Client Activity

```python
import json
from collections import Counter

# Count requests per client
client_counts = Counter()

with open('logs/_server.log', 'r') as f:
    for line in f:
        entry = json.loads(line.strip())
        client_counts[entry['client_name']] += 1

# Print top clients
for client, count in client_counts.most_common():
    print(f"{client}: {count} requests")
```

---

## Performance Considerations

### Logging Impact

- **Lightweight**: Minimal performance impact on server operations
- **Non-blocking**: Failed logging attempts don't break server
- **Async writes**: Log writes don't block request processing
- **One entry per request**: Predictable log growth

### Log Rotation

- **Maximum size**: 10 MB per log file
- **Backup count**: 5 rotated files kept
- **Compression**: Rotated files automatically gzip-compressed
- **Automatic cleanup**: Oldest files deleted when backup limit reached

### Storage Estimates

Assuming average log entry size of ~250 bytes:

| Requests/Day | Daily Log Size | Monthly Log Size (compressed) |
|--------------|----------------|-------------------------------|
| 10,000 | ~2.5 MB | ~25 MB |
| 100,000 | ~25 MB | ~250 MB |
| 1,000,000 | ~250 MB | ~2.5 GB |

Compression typically reduces size by 70-80%.

---

## Monitoring and Analysis

### Use Cases

**1. Performance Analysis**
- Track request durations to identify bottlenecks
- Compare method performance over time
- Identify slow operations needing optimization

**2. Usage Patterns**
- Analyze which methods are called most frequently
- Understand client behavior patterns
- Identify peak usage times

**3. Error Tracking**
- Identify failed requests (status_code: 500)
- Correlate errors with specific clients or methods
- Debug issues with stack traces in error field

**4. Simulation Progress**
- Monitor day/hour progression
- Track simulation advancement rate
- Verify proper time slot transitions

**5. Client Behavior**
- Track which clients are making requests
- Identify inactive or problematic clients
- Analyze client-specific patterns

**6. Debugging**
- Correlate client issues with server-side logs
- Trace request flows through request_id
- Verify proper client registration/deregistration

### Recommended Monitoring

**Real-time Monitoring:**
```bash
# Follow log in real-time
tail -f logs/_server.log | jq .

# Monitor for errors
tail -f logs/_server.log | jq 'select(.status_code == 500)'

# Watch specific client
tail -f logs/_server.log | jq 'select(.client_name == "client_1")'
```

**Periodic Analysis:**
- Daily summary of request counts by method
- Weekly performance trend analysis
- Monthly error rate tracking
- Client activity reports

---

## Configuration

### Enabling/Disabling Request Logging

Request logging is controlled in `server_config.json`:

```json
{
  "logging": {
    "enable_request_log": true
  }
}
```

Set to `false` to disable request logging entirely. This can reduce disk I/O in large-scale simulations.

**See [LOGGING_CONFIG.md](LOGGING_CONFIG.md) for complete logging configuration options.**

### Error Handling

- **Failed logging doesn't crash server**: Simulation continues even if logging fails
- **Stderr fallback**: Logging errors reported to stderr for debugging
- **Graceful degradation**: Server operates normally without logging

---

## Related Documentation

- **[LOGGING_CONFIG.md](LOGGING_CONFIG.md)** - Complete logging configuration guide
- **[ACTION_LOGGING.md](ACTION_LOGGING.md)** - Client action log format
- **[CONFIG.md](CONFIG.md)** - Server configuration guide

---

## Technical Details

### Implementation

Request logging is implemented using a Python decorator that wraps logged methods:

```python
@log_server_request
def register_client(self, client_id: str):
    # Method implementation
    ...
```

The decorator:
1. Generates unique request ID
2. Records start time
3. Executes the wrapped method
4. Calculates duration
5. Extracts simulation context
6. Writes JSON log entry
7. Handles errors gracefully

### Log File Format

- **Format**: JSON Lines (JSONL)
- **Encoding**: UTF-8
- **Line endings**: Unix (LF)
- **One JSON object per line**: Easy to parse with streaming
- **No array wrapping**: Direct line-by-line processing

### Backward Compatibility

- `client_id` parameter is optional on all methods
- Existing code works without modification
- Gradual migration to full client traceability
- "unknown" client_name for legacy calls
