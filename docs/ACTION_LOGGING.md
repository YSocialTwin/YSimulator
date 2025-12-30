# Client Action Logging

This document describes the action logging system that tracks individual agent actions and provides hourly and daily summaries.

## Overview

The client action logging system creates a separate log file (`{client_id}_actions.log`) that contains:
1. Individual action entries for each agent action
2. Hourly summaries with aggregated statistics
3. Daily summaries with day-wide statistics

## Log File Location

Action logs are created in the logs directory alongside other client logs:
- Path: `{config_path}/logs/{client_id}_actions.log`
- Example: `./example/logs/client_1_actions.log`

## Log Entry Formats

### Individual Action Entry

Each agent action is logged with the following JSON format:

```json
{"time": "2025-12-01 10:39:50", "agent_name": "MarisaSoto", "method_name": "post", "execution_time_seconds": 0.0086, "success": true}
```

Fields:
- `time`: Timestamp in format `YYYY-MM-DD HH:MM:SS`
- `agent_name`: Username of the agent performing the action
- `method_name`: Type of action (post, comment, read, follow, share, search, etc.)
- `execution_time_seconds`: Time taken to execute the action in seconds
- `success`: Boolean indicating whether the action succeeded

### Hourly Summary

At the end of each hour (slot), an hourly summary is logged:

```json
{
  "time": "2025-12-01 10:59:59",
  "summary_type": "hourly",
  "day": 0,
  "slot": 10,
  "total_actions": 100,
  "successful_actions": 98,
  "total_execution_time_seconds": 0.8632,
  "average_execution_time_seconds": 0.0086,
  "actions_by_method": {
    "post": 30,
    "comment": 25,
    "read": 25,
    "follow": 20
  }
}
```

Fields:
- `time`: Timestamp when the summary was generated
- `summary_type`: Always `"hourly"` for hourly summaries
- `day`: Simulation day number
- `slot`: Simulation slot (hour) number
- `total_actions`: Total number of actions in this hour
- `successful_actions`: Number of successful actions
- `total_execution_time_seconds`: Sum of execution times for all actions
- `average_execution_time_seconds`: Average execution time per action
- `actions_by_method`: Dictionary mapping method names to their counts

### Daily Summary

At the end of each day, a daily summary is logged:

```json
{
  "time": "2025-12-01 23:59:59",
  "summary_type": "daily",
  "day": 0,
  "total_actions": 2400,
  "successful_actions": 2380,
  "total_execution_time_seconds": 20.712,
  "average_execution_time_seconds": 0.0086,
  "actions_by_method": {
    "post": 720,
    "comment": 600,
    "read": 600,
    "follow": 480
  }
}
```

Fields:
- `time`: Timestamp when the summary was generated
- `summary_type`: Always `"daily"` for daily summaries
- `day`: Simulation day number
- `total_actions`: Total number of actions across the entire day
- `successful_actions`: Number of successful actions
- `total_execution_time_seconds`: Sum of execution times for all actions
- `average_execution_time_seconds`: Average execution time per action
- `actions_by_method`: Dictionary mapping method names to their counts

## Usage

The action logging system is automatically enabled for all simulation clients. No configuration is required.

### Reading Log Files

Since each line in the action log is a valid JSON object, you can easily parse and analyze the logs:

```python
import json

# Read and parse action log
with open('logs/client_1_actions.log', 'r') as f:
    for line in f:
        entry = json.loads(line)
        
        if entry.get('summary_type') == 'hourly':
            print(f"Hourly summary for day {entry['day']}, slot {entry['slot']}")
            print(f"  Total actions: {entry['total_actions']}")
        elif entry.get('summary_type') == 'daily':
            print(f"Daily summary for day {entry['day']}")
            print(f"  Total actions: {entry['total_actions']}")
        else:
            print(f"{entry['time']}: {entry['agent_name']} performed {entry['method_name']}")
```

### Analyzing Performance

Example script to calculate average execution times by method:

```python
import json
from collections import defaultdict

method_times = defaultdict(list)

with open('logs/client_1_actions.log', 'r') as f:
    for line in f:
        entry = json.loads(line)
        if 'method_name' in entry:  # Individual action, not a summary
            method_times[entry['method_name']].append(entry['execution_time_seconds'])

for method, times in method_times.items():
    avg_time = sum(times) / len(times)
    print(f"{method}: {avg_time:.4f}s average ({len(times)} actions)")
```

## Implementation Notes

- Execution times are estimated by dividing the total simulation time for a slot by the number of actions
- All actions that are submitted to the server are logged as successful
- The action logger uses log rotation (10MB per file, 5 backup files)
- Log entries use `datetime.now()` for timestamps, which reflects the actual wall-clock time
- Hourly and daily statistics are reset after each summary is logged

## Performance Impact

The action logging system has minimal performance impact:
- Logging is asynchronous via Python's logging framework
- JSON serialization is fast and efficient
- Log rotation prevents unbounded disk usage
- No additional network calls or database queries are required
