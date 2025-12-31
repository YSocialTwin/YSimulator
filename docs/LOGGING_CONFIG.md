# YSimulator Logging Configuration

## Overview

YSimulator provides a comprehensive logging system that tracks simulation execution, agent actions, and server requests. All logging is configurable and can be customized through configuration files to balance observability with performance requirements.

### Why Configure Logging?

Logging configuration allows you to:
- **Reduce disk I/O** in large-scale simulations where write operations become a bottleneck
- **Save storage space** in resource-constrained environments
- **Focus on relevant logs** for specific debugging or analysis tasks
- **Minimize performance impact** by disabling detailed logs when not needed

### Default Behavior

**All logs are enabled by default.** If you don't specify a logging configuration, YSimulator will create all log files with full details.

---

## Configuration Files

YSimulator uses two separate configuration files for logging:

1. **`simulation_config.json`** - Controls client-side logging
2. **`server_config.json`** - Controls server-side logging

Each can be configured independently, allowing you to enable detailed logging on the server while minimizing client logs, or vice versa.

---

## Client Logging Configuration

### Configuration File: `simulation_config.json`

Client logging is configured by adding a `logging` section to your `simulation_config.json` file:

```json
{
  "client_name": "client_1",
  "namespace": "social_sim",
  "llm": { ... },
  "simulation": { ... },
  "agents": { ... },
  "logging": {
    "enable_execution_log": true,
    "enable_actor_log": true,
    "enable_client_log": true,
    "enable_console_log": true
  }
}
```

### Client Log Files

The client creates three types of log files:

#### 1. Execution Log: `{client_name}_execution.log`

**Purpose**: High-level client startup and lifecycle events

**Configuration**: `enable_execution_log` (default: `true`)

**Contains**:
- Configuration loading events
- Client initialization and shutdown
- Connection status to server
- High-level errors and warnings

**Use when**: You need to debug client startup issues or track client lifecycle

#### 2. Actor Log: `{client_id}_actor.log`

**Purpose**: Detailed simulation execution tracking

**Configuration**: `enable_actor_log` (default: `true`)

**Contains**:
- Round progression events
- Agent scheduling and execution
- Simulation state changes
- Internal actor operations

**Use when**: You need detailed simulation flow information or debugging agent execution order

#### 3. Client Log: `{client_id}_client.log`

**Purpose**: Individual agent action tracking

**Configuration**: `enable_client_log` (default: `true`)

**Contains**:
- Every agent action (posts, comments, follows, etc.)
- Action execution times
- Success/failure status
- Hourly and daily summaries

**Use when**: You need to analyze agent behavior, action patterns, or performance metrics

**Note**: This log was formerly named `{client_id}_actions.log`. See [ACTION_LOGGING.md](ACTION_LOGGING.md) for detailed format.

#### 4. Console Output

**Purpose**: Real-time monitoring in terminal

**Configuration**: `enable_console_log` (default: `true`)

**Contains**: Formatted log messages displayed in the console

**Use when**: You want to monitor execution in real-time or reduce terminal output noise

---

## Server Logging Configuration

### Configuration File: `server_config.json`

Server logging is configured by adding a `logging` section to your `server_config.json` file:

```json
{
  "server_name": "orchestrator_server",
  "namespace": "social_sim",
  "database": { ... },
  "redis": { ... },
  "logging": {
    "enable_server_log": true,
    "enable_actor_log": true,
    "enable_request_log": true,
    "enable_console_log": true
  }
}
```

### Server Log Files

The server creates three types of log files:

#### 1. Server Log: `{server_name}_server.log`

**Purpose**: High-level server startup and lifecycle events

**Configuration**: `enable_server_log` (default: `true`)

**Contains**:
- Configuration loading events
- Database connection status
- Server initialization and shutdown
- Ray actor creation
- High-level errors and warnings

**Use when**: You need to debug server startup issues or track server lifecycle

#### 2. Actor Log: `{server_name}_actor.log`

**Purpose**: Detailed orchestrator operations

**Configuration**: `enable_actor_log` (default: `true`)

**Contains**:
- Client registration and deregistration
- Round management and progression
- Agent coordination events
- Internal orchestrator operations

**Use when**: You need detailed orchestration flow information or debugging multi-client coordination

#### 3. Request Log: `_server.log`

**Purpose**: Complete request tracking with client traceability

**Configuration**: `enable_request_log` (default: `true`)

**Contains**:
- Every server method call
- Request timing and duration
- Client identification
- Simulation context (day, hour, round ID)
- Success/failure status

**Use when**: You need to trace client interactions, analyze performance, or debug request issues

**Note**: See [SERVER_LOGGING.md](SERVER_LOGGING.md) for detailed request log format and analysis examples.

#### 4. Console Output

**Purpose**: Real-time monitoring in terminal

**Configuration**: `enable_console_log` (default: `true`)

**Contains**: Formatted log messages displayed in the console

**Use when**: You want to monitor server activity in real-time or reduce terminal output noise

---

## Log File Management

### Rotation and Compression

All log files automatically rotate and compress to save disk space:

- **Rotation threshold**: 10 MB per log file
- **Backup count**: 5 rotated files kept
- **Compression**: Rotated files are gzip-compressed with `.gz` extension

**Example**:
```
logs/
├── client_1_client.log         # Current log file
├── client_1_client.log.1.gz    # Most recent backup
├── client_1_client.log.2.gz
├── client_1_client.log.3.gz
├── client_1_client.log.4.gz
└── client_1_client.log.5.gz    # Oldest backup
```

### Working with Compressed Logs

Decompress a rotated log file:
```bash
gunzip logs/client_1_client.log.1.gz
```

View compressed log without decompressing:
```bash
zcat logs/client_1_client.log.1.gz | less
```

Search in compressed logs:
```bash
zgrep "error" logs/client_1_client.log.*.gz
```

---

## Configuration Examples

### Example 1: Default Configuration (All Logs Enabled)

Simply omit the `logging` section, or explicitly enable all:

**Client** (`simulation_config.json`):
```json
{
  "logging": {
    "enable_execution_log": true,
    "enable_actor_log": true,
    "enable_client_log": true,
    "enable_console_log": true
  }
}
```

**Server** (`server_config.json`):
```json
{
  "logging": {
    "enable_server_log": true,
    "enable_actor_log": true,
    "enable_request_log": true,
    "enable_console_log": true
  }
}
```

**Best for**: Development, debugging, and small-scale simulations

---

### Example 2: Minimal Logging (Essential Logs Only)

Keep only high-level execution logs, disable detailed tracking:

**Client** (`simulation_config.json`):
```json
{
  "logging": {
    "enable_execution_log": true,
    "enable_actor_log": false,
    "enable_client_log": false,
    "enable_console_log": false
  }
}
```

**Server** (`server_config.json`):
```json
{
  "logging": {
    "enable_server_log": true,
    "enable_actor_log": false,
    "enable_request_log": false,
    "enable_console_log": false
  }
}
```

**Best for**: Large-scale simulations where disk I/O is a concern, but you still need lifecycle tracking

---

### Example 3: Performance Analysis Mode

Enable request tracking for performance analysis, disable action details:

**Client** (`simulation_config.json`):
```json
{
  "logging": {
    "enable_execution_log": false,
    "enable_actor_log": false,
    "enable_client_log": false,
    "enable_console_log": true
  }
}
```

**Server** (`server_config.json`):
```json
{
  "logging": {
    "enable_server_log": true,
    "enable_actor_log": false,
    "enable_request_log": true,
    "enable_console_log": true
  }
}
```

**Best for**: Analyzing server performance and request patterns without generating large client logs

---

### Example 4: Console-Only Mode

Disable all file logging, use only console output:

**Client** (`simulation_config.json`):
```json
{
  "logging": {
    "enable_execution_log": false,
    "enable_actor_log": false,
    "enable_client_log": false,
    "enable_console_log": true
  }
}
```

**Server** (`server_config.json`):
```json
{
  "logging": {
    "enable_server_log": false,
    "enable_actor_log": false,
    "enable_request_log": false,
    "enable_console_log": true
  }
}
```

**Best for**: Real-time monitoring without persistent storage, or testing scenarios

---

## Implementation Details

### Configuration Precedence

1. If the `logging` section exists, use specified values
2. If a specific option is omitted, default to `true`
3. If the entire `logging` section is omitted, all logs are enabled

### Runtime Behavior

- **Changes require restart**: Logging configuration is read at startup
- **Loggers always created**: Even disabled logs create logger objects (for code compatibility)
- **No file writes when disabled**: Disabled logs don't create files or write data
- **Independent control**: Each log type can be enabled/disabled independently

### Error Handling

- Failed logging attempts don't crash the simulation
- Logging errors are reported to stderr for debugging
- Simulation continues even if logging completely fails

---

## Related Documentation

- **[SERVER_LOGGING.md](SERVER_LOGGING.md)** - Detailed server request log format and analysis
- **[ACTION_LOGGING.md](ACTION_LOGGING.md)** - Client action log format and summaries
- **[CONFIG.md](CONFIG.md)** - Complete configuration guide for all YSimulator settings

---

## Quick Reference

### Client Logging Options

| Option | File | Purpose | Default |
|--------|------|---------|---------|
| `enable_execution_log` | `{client_name}_execution.log` | High-level client lifecycle | `true` |
| `enable_actor_log` | `{client_id}_actor.log` | Detailed simulation execution | `true` |
| `enable_client_log` | `{client_id}_client.log` | Agent action tracking | `true` |
| `enable_console_log` | (console) | Terminal output | `true` |

### Server Logging Options

| Option | File | Purpose | Default |
|--------|------|---------|---------|
| `enable_server_log` | `{server_name}_server.log` | High-level server lifecycle | `true` |
| `enable_actor_log` | `{server_name}_actor.log` | Detailed orchestrator operations | `true` |
| `enable_request_log` | `_server.log` | Request tracking with timing | `true` |
| `enable_console_log` | (console) | Terminal output | `true` |

### Log Rotation Settings

| Setting | Value |
|---------|-------|
| Rotation size | 10 MB |
| Backup count | 5 files |
| Compression | gzip (.gz) |
| Format | JSON (one entry per line) |
