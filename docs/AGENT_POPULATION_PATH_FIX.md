# Agent Population File Path Handling

## Issue Fixed
When starting the client with a custom agent population file via the `--agents` parameter, updates to agent data (e.g., updated interests at end of day) were not being saved back to the custom file. Instead, the system was looking for the file in the default config directory with standard naming conventions.

## Root Cause
The custom file path provided via `--agents` parameter was used to load the initial configuration but was not stored for later save operations. When `save_updated_agent_population()` was called, it only looked in the config directory for:
1. `{client_id}_agent_population.json` (client-specific)
2. `agent_population.json` (generic)

## Solution
The custom agent_config_file path is now passed through the initialization chain and stored for use in save operations:

```
run_client.py 
  → SimulationClient.__init__(agent_config_file_path)
    → AgentManager.__init__(agent_config_file_path)
      → PopulationLoader.__init__(agent_config_file_path)
        → _get_agent_config_file() uses stored path
```

## File Resolution Priority
When determining which agent_population.json file to use, the system now follows this priority:

1. **Custom path** (if provided via `--agents` parameter) - **NEW**
2. Client-specific file: `{client_id}_agent_population.json` in config_path
3. Generic file: `agent_population.json` in config_path
4. None (file not found)

## Usage Examples

### With Custom Path
```bash
python run_client.py --config /app/config --agents /custom/path/my_agents.json
```
- Loads from: `/custom/path/my_agents.json`
- Saves to: `/custom/path/my_agents.json` ✅

### Without Custom Path (Default Behavior)
```bash
python run_client.py --config /app/config
```
- Looks for: `/app/config/{client_name}_agent_population.json`
- Falls back to: `/app/config/agent_population.json`
- Behavior unchanged from before ✅

## Modified Files
1. `run_client.py` - Pass agent_config_file path to SimulationClient
2. `YSimulator/YClient/client.py` - Accept and store agent_config_file_path
3. `YSimulator/YClient/agent_management/agent_manager.py` - Pass to PopulationLoader
4. `YSimulator/YClient/agent_management/population_loader.py` - Use stored path

## Backward Compatibility
All changes are backward compatible:
- New parameters are optional with default value `None`
- Existing code without custom paths continues to work
- Tests using default behavior should pass without modification
