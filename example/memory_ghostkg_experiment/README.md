# Memory GhostKG Experiment

This experiment demonstrates YSimulator semantic memory using the `ghostkg` backend adapter.

## What This Config Tests

- GhostKG-backed event ingestion and memory retrieval
- prompt-level memory context injection from GhostKG
- compatibility with tuple-based simulation time `(day, hour)`
- extraction mode configuration (`triplets`, `fast`, `llm`)

## Files in This Folder

- `server_config.json`: server setup with dedicated SQLite DB filename
- `simulation_config.json`: client simulation config with `agent_memory.backend = ghostkg`

## Run

```bash
python run_server.py --config example/memory_ghostkg_experiment/server_config.json
```

```bash
python run_client.py \
  --config example/memory_ghostkg_experiment/simulation_config.json \
  --agents example/memory_ghostkg_experiment/agent_population.json \
  --prompts example/memory_ghostkg_experiment/prompts.json
```

## GhostKG Configuration Modes

Configured default in this experiment:

- `agent_memory.ghostkg.extraction_mode = "fast"`

Alternatives:

- `triplets`: deterministic and lowest cost
- `fast`: low-cost text extraction
- `llm`: highest semantic flexibility; requires provider/model/API setup

If `llm` mode is used, configure:

- `llm_provider`
- `llm_model`
- `llm_base_url`
- `llm_api_key` or `llm_api_key_env`

## Suggested Checks

- Call server memory status API and confirm backend `ghostkg`.
- Verify memory snippets appear in prompts.
- Compare behavior/cost by switching `extraction_mode`.
