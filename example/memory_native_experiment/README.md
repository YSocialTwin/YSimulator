# Memory Native Experiment

This experiment demonstrates YSimulator semantic memory with the built-in `native` backend.

## What This Config Tests

- SQL-backed memory ingestion from agent actions
- memory retrieval for LLM prompt conditioning
- reinforcement of used memory snippets
- periodic forgetting (decay, soft forget, hard delete)

## Files in This Folder

- `server_config.json`: server setup with dedicated SQLite DB filename
- `simulation_config.json`: client simulation config with `agent_memory.backend = native`

## Run

```bash
python run_server.py --config example/memory_native_experiment/server_config.json
```

```bash
python run_client.py \
  --config example/memory_native_experiment/simulation_config.json \
  --agents example/memory_native_experiment/agent_population.json \
  --prompts example/memory_native_experiment/prompts.json
```

## Key Parameters

In `simulation_config.json`:

- `agent_memory.enabled`: `true`
- `agent_memory.backend`: `native`
- `agent_memory.retrieval_top_k`: `5`
- `agent_memory.forgetting_cycle_interval_rounds`: `24`
- `agent_memory.time_decay_lambda`: `0.015`
- `agent_memory.reinforce_gain`: `0.08`

## Suggested Checks

- Call server memory status API and confirm backend `native`.
- Verify memory context appears in LLM prompts.
- Verify forgetting stats are logged every configured interval.
