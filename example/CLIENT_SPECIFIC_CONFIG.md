# Client-Specific Configuration Example

This directory demonstrates how to use client-specific configuration files.

## Setup

When you have multiple clients running in the same configuration directory, each client can have its own:
- Agent population
- LLM prompts
- Social network topology

## File Naming Convention

For a client named "client_1" (defined in simulation_config.json):

- `client_1_agent_population.json` - Custom agent population for this client
- `client_1_llm_prompts.json` - Custom LLM prompts for this client
- `client_1_network.csv` - Custom social network for this client

If these files don't exist, the client will use the generic files:
- `agent_population.json`
- `llm_prompts.json`
- `network.csv`

## Example Usage

### Scenario: Two clients with different agent populations

**Directory structure:**
```
my_config/
├── simulation_config.json          (client_name: "client_1")
├── agent_population.json           (Generic agents - fallback)
├── client_1_agent_population.json  (Custom agents for client_1)
├── client_2_agent_population.json  (Custom agents for client_2)
├── llm_prompts.json                (Shared by all clients)
└── network.csv                     (Shared by all clients)
```

**Start client 1:**
```bash
# Edit simulation_config.json to set "client_name": "client_1"
python run_client.py --config my_config
# Uses: client_1_agent_population.json, llm_prompts.json, network.csv
```

**Start client 2:**
```bash
# Edit simulation_config.json to set "client_name": "client_2"
python run_client.py --config my_config
# Uses: client_2_agent_population.json, llm_prompts.json, network.csv
```

## Benefits

1. **Different agent populations per client** - Useful for distributed simulations
2. **Different LLM behaviors** - Each client can have different prompts
3. **Different social networks** - Each client can initialize different follow relationships
4. **Easy fallback** - Missing client-specific files fall back to generic ones
5. **Clean organization** - All configs in one directory
