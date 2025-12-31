# YSimulator Logging Configuration

This document describes the optional logging configuration that can be added to `simulation_config.json` and `server_config.json`.

## Overview

All log files are optional and enabled by default. Logging can be disabled for individual log files to reduce write operations, which can be useful for:
- Large-scale simulations where disk I/O is a bottleneck
- Running simulations in resource-constrained environments
- Testing scenarios where logging is not needed

## Configuration Format

### Client Logging (simulation_config.json)

Add a `logging` section to your `simulation_config.json`:

```json
{
  "client_name": "client_1",
  "logging": {
    "enable_execution_log": true,
    "enable_actor_log": true,
    "enable_client_log": true,
    "enable_console_log": true
  },
  "simulation": {
    ...
  }
}
```

#### Client Logging Options

- **`enable_execution_log`** (default: `true`)
  - Controls the `{client_name}_execution.log` file
  - Contains high-level client execution logs from `run_client.py`
  - Logs configuration loading, client startup, and shutdown events

- **`enable_actor_log`** (default: `true`)
  - Controls the `{client_id}_actor.log` file
  - Contains detailed simulation client actor logs
  - Logs agent actions, round progression, and simulation events

- **`enable_client_log`** (default: `true`)
  - Controls the `{client_id}_client.log` file
  - Contains individual agent action logs (formerly `_actions.log`)
  - Logs each agent's posts, comments, reactions, follows, etc.

- **`enable_console_log`** (default: `true`)
  - Controls console output from the client
  - When disabled, reduces stdout noise

### Server Logging (server_config.json)

Add a `logging` section to your `server_config.json`:

```json
{
  "server_name": "orchestrator_server",
  "logging": {
    "enable_server_log": true,
    "enable_actor_log": true,
    "enable_request_log": true,
    "enable_console_log": true
  },
  "database": {
    ...
  }
}
```

#### Server Logging Options

- **`enable_server_log`** (default: `true`)
  - Controls the `{server_name}_server.log` file
  - Contains high-level server logs from `run_server.py`
  - Logs server startup, configuration loading, and actor initialization

- **`enable_actor_log`** (default: `true`)
  - Controls the `{server_name}_actor.log` file
  - Contains orchestrator actor logs
  - Logs client registration, round management, and coordination events

- **`enable_request_log`** (default: `true`)
  - Controls the `_server.log` file
  - Contains individual request logs with client traceability
  - Logs all server method calls with timing and status information

- **`enable_console_log`** (default: `true`)
  - Controls console output from the server
  - When disabled, reduces stdout noise

## Example: Minimal Logging Configuration

To minimize disk writes while maintaining essential debugging capability:

### Client (simulation_config.json)
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

### Server (server_config.json)
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

This configuration keeps only the high-level execution logs active.

## Example: No Logging Configuration

To disable all file logging (console only):

### Client (simulation_config.json)
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

### Server (server_config.json)
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

## Log File Compression

All rotating log files are automatically compressed with gzip when they rotate (at 10MB size threshold). Compressed files have a `.gz` extension and can be decompressed with:

```bash
gunzip filename.log.1.gz
```

Or viewed directly with:

```bash
zcat filename.log.1.gz | less
```

## Notes

- If the `logging` section is omitted, all logging is enabled by default
- Individual logging options can be omitted, and they will default to `true`
- Loggers are created even when disabled, but they don't write to files
- Console logging can be independently controlled from file logging
- Changes to logging configuration require restarting the client or server
