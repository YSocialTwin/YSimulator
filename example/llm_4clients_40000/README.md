# Multi-Client vLLM Population Experiment (4 Clients × 10,000 Agents)

This experiment demonstrates a large-scale YSimulator configuration with **parallel client execution using vLLM**:
- **40,004 agents total**: **40,000 LLM-enabled agents** across 4 clients + **4 news pages** (one per client)
- **vLLM backend**: High-performance LLM inference with ~30x speedup vs sequential Ollama
- **Initial shared social network** with ~400,000 follow relationships (~10 connections per agent)
- **Discussion topics**: war, politics, sport, books, movies
- **Dynamic follow actions** using multiple recommendation strategies
- **Agent archetypes**: Validator, Broadcaster, Explorer
- **LLM-based opinion dynamics**: Natural language opinion evaluation
- **Parallel execution**: Each client runs independently managing 10,000 agents

## Architecture

This experiment is designed to demonstrate YSimulator's ability to scale horizontally by distributing agents across multiple clients that run in parallel. Each client:
- Manages its own subset of 10,000 agents (+ 1 news page)
- Has its own configuration file and agent population file
- Creates its own log files (automatically separated by `client_name`)
- Connects to the same shared Ray server
- Shares the same social network topology

### Agent Distribution

| Client | Agents | Page Agent | Agent IDs |
|--------|--------|------------|-----------|
| client_1 | 10,000 | NewsPage_Client1 | agent_00000 - agent_09999 |
| client_2 | 10,000 | NewsPage_Client2 | agent_10000 - agent_19999 |
| client_3 | 10,000 | NewsPage_Client3 | agent_20000 - agent_29999 |
| client_4 | 10,000 | NewsPage_Client4 | agent_30000 - agent_39999 |
| **Total** | **40,000** | **4 pages** | **40,004 total** |

## Quick Start

### 1. Generate Configuration

```bash
cd example/llm_4clients_40000
python generate_population.py
```

This creates:
- `client_1_agent_population.json` through `client_4_agent_population.json` - Agent definitions (one per client)
- `client_1_simulation_config.json` through `client_4_simulation_config.json` - Simulation parameters (one per client)
- `network.csv` - Shared initial social network (~400,000 edges)
- `server_config.json` - Server settings (configured for 4 clients)

**Note**: Generation may take several minutes due to the large network size (~400,000 edges).

### 2. Start Server

```bash
# From repository root
python run_server.py --config example/llm_4clients_40000
```

**Server Configuration Notes:**
- The server automatically creates `ray_config.temp` in the config directory
- This file contains the Ray cluster address and is automatically used by clients
- The default `server_config.json` has `"address": "auto"` which starts a new Ray cluster
- Ray will assign a random port when starting a new cluster
- **To use a specific port**: Start Ray externally first, then set `"address": "auto"` in config
  ```bash
  # Start Ray on specific port (in a separate terminal)
  ray start --head --port=40233 --node-ip-address=146.48.83.173
  
  # Then set in server_config.json:
  # "address": "auto"  (will connect to the externally started Ray)
  ```
- **To connect to existing Ray cluster**: Set address and port in config
  ```json
  "address": "146.48.83.173",
  "port": 40233
  ```

**Important**: The server is configured with `min_to_start: 1`, allowing clients to start sequentially. This enables GPU actor reuse when `"reuse_actors": true` is set in client configurations - the first client creates the GPU actors, and subsequent clients reuse them.

The server will display its Ray address:
```
--- 🚀 Server Running on 146.48.83.173:40233 ---
```

### 3. Start Clients (No Configuration Update Needed!)

**Good news**: If you run the clients from the same config directory as the server, they will automatically use the `ray_config.temp` file. No manual configuration needed!

However, if you want to manually set the server address or run clients from a different directory, update the client configuration files:

```bash
# Edit each client configuration file
nano example/llm_4clients_40000/client_1_simulation_config.json
# Set "server": {"address": "127.0.0.1", "port": 10001}
# (Get the address and port from server startup output)
# Repeat for client_2, client_3, client_4
```

Or use this quick command to update all files (replace with your actual server address and port):
```bash
cd example/llm_4clients_40000
# Replace 127.0.0.1 and 10001 with your actual server address and port
SERVER_ADDR="127.0.0.1"
SERVER_PORT="10001"
for i in 1 2 3 4; do
  jq --arg addr "$SERVER_ADDR" --arg port "$SERVER_PORT" \
    '.server.address = $addr | .server.port = ($port | tonumber)' \
    client_${i}_simulation_config.json > tmp_${i}.json && \
    mv tmp_${i}.json client_${i}_simulation_config.json
done
```

**Alternative format**: You can also use the full Ray URL format:
```bash
# Set "server": {"address": "ray://127.0.0.1:10001", "port": null}
```

### 4. Start Clients in Parallel

Open 4 separate terminal windows and start each client:

**Terminal 1 - Client 1:**
```bash
python run_client.py \
  --config example/llm_4clients_40000/client_1_simulation_config.json \
  --agents example/llm_4clients_40000/client_1_agent_population.json \
  --prompts example/llm_4clients_40000/prompts.json
```

**Terminal 2 - Client 2:**
```bash
python run_client.py \
  --config example/llm_4clients_40000/client_2_simulation_config.json \
  --agents example/llm_4clients_40000/client_2_agent_population.json \
  --prompts example/llm_4clients_40000/prompts.json
```

**Terminal 3 - Client 3:**
```bash
python run_client.py \
  --config example/llm_4clients_40000/client_3_simulation_config.json \
  --agents example/llm_4clients_40000/client_3_agent_population.json \
  --prompts example/llm_4clients_40000/prompts.json
```

**Terminal 4 - Client 4:**
```bash
python run_client.py \
  --config example/llm_4clients_40000/client_4_simulation_config.json \
  --agents example/llm_4clients_40000/client_4_agent_population.json \
  --prompts example/llm_4clients_40000/prompts.json
```

**Alternative: Use a shell script or tmux/screen to manage multiple terminals**

Create a `start_all_clients.sh` script:
```bash
#!/bin/bash
# Start all clients in the background

cd "$(dirname "$0")/../.."

python run_client.py \
  --config example/llm_4clients_40000/client_1_simulation_config.json \
  --agents example/llm_4clients_40000/client_1_agent_population.json \
  --prompts example/llm_4clients_40000/prompts.json &

python run_client.py \
  --config example/llm_4clients_40000/client_2_simulation_config.json \
  --agents example/llm_4clients_40000/client_2_agent_population.json \
  --prompts example/llm_4clients_40000/prompts.json &

python run_client.py \
  --config example/llm_4clients_40000/client_3_simulation_config.json \
  --agents example/llm_4clients_40000/client_3_agent_population.json \
  --prompts example/llm_4clients_40000/prompts.json &

python run_client.py \
  --config example/llm_4clients_40000/client_4_simulation_config.json \
  --agents example/llm_4clients_40000/client_4_agent_population.json \
  --prompts example/llm_4clients_40000/prompts.json &

wait
```

## vLLM Configuration

This experiment uses vLLM for high-performance LLM inference. Each client is configured with:

- **Model**: AMead10/Llama-3.2-3B-Instruct-AWQ (quantized for efficiency)
- **num_actors**: 4 vLLM instances per client for parallel processing
- **gpu_per_actor**: 1.0 (adjust to 0.25 to fit 4 actors on 1 GPU)
- **actor_name_prefix**: Unique per client (e.g., `ysim_llm_client1`) to avoid conflicts
- **reuse_actors**: false by default (each client starts its own vLLM instances)

**GPU Requirements:**
- **Option 1**: 4 GPUs per client (16 GPUs total) with `gpu_per_actor: 1`
- **Option 2**: 1 GPU per client (4 GPUs total) with `gpu_per_actor: 0.25`
- **Option 3 (GPU Actor Reuse)**: Share GPU actors across clients
  - Set `"reuse_actors": true` in client_2, client_3, client_4 configurations
  - Set the same `actor_name_prefix` across all clients (e.g., `"ysim_llm_shared"`)
  - Start clients sequentially (not in parallel) - client_1 creates actors, others reuse them
  - **Note**: Server must have `min_to_start: 1` to allow sequential client startup (already configured)

**Performance Notes:**
- vLLM provides ~30x speedup compared to sequential Ollama
- With 4 actors per client, each client can process agent actions in parallel
- Total: 16 vLLM actors across 4 clients for maximum throughput (or 4 actors shared if using reuse_actors)

## Log Files

Each client automatically creates separate log files based on its `client_name`:

```
example/llm_4clients_40000/logs/
├── orchestrator_server_server.log      # Server execution log
├── orchestrator_server_actor.log       # Server actor log
├── _server.log                         # Server request log
├── client_1_execution.log              # Client 1 execution log
├── client_1_actor.log                  # Client 1 actor log
├── client_1_client.log                 # Client 1 action log
├── client_2_execution.log              # Client 2 execution log
├── client_2_actor.log                  # Client 2 actor log
├── client_2_client.log                 # Client 2 action log
├── client_3_execution.log              # Client 3 execution log
├── client_3_actor.log                  # Client 3 actor log
├── client_3_client.log                 # Client 3 action log
├── client_4_execution.log              # Client 4 execution log
├── client_4_actor.log                  # Client 4 actor log
└── client_4_client.log                 # Client 4 action log
```

**Key Feature**: The `client_name` in each configuration file (`client_1`, `client_2`, etc.) automatically ensures that log files don't conflict when running clients in parallel.

## Configuration Files

### Agent Population Files

Each client has its own agent population file:
- `client_1_agent_population.json`: agents 00000-09999 + NewsPage_Client1
- `client_2_agent_population.json`: agents 10000-19999 + NewsPage_Client2
- `client_3_agent_population.json`: agents 20000-29999 + NewsPage_Client3
- `client_4_agent_population.json`: agents 30000-39999 + NewsPage_Client4

Each file contains 10,001 agents with diverse characteristics:
- Political leanings: left, center, right, neutral
- Activity profiles: Always On, Morning Active, Evening Active
- Professions: Engineer, Teacher, Doctor, Artist, Student
- Content recommendation: random, rchrono, rchrono_followers
- Follow recommendation: random, common_neighbors, jaccard, adamic_adar, preferential_attachment

### Network Topology

`network.csv` contains a **shared** social network with approximately 400,000 directed follow edges using Erdős–Rényi random graph model. This network spans all agents across all clients, enabling cross-client interactions.

### Simulation Config Files

Each client has its own configuration file (`client_N_simulation_config.json`) with:
- **Unique `client_name`**: Ensures log file separation
- **Shared namespace**: All clients use "social_sim" namespace
- **Server address**: Must be set to the Ray server address
- **Simulation parameters**:
  - Duration: 3 days, 24 slots per day (72 rounds)
  - Discussion topics: war, politics, sport, books, movies
  - Action likelihoods: post (3.0), comment (5.0), read (2.0), share (1.0), search (5.0), follow (0.1)
  - Follow probabilities: 10% daily, 10% secondary after interactions

### Server Configuration

`server_config.json` includes:
- **Database**: SQLite (configurable for PostgreSQL/MySQL)
- **min_to_start**: 1 (allows clients to start sequentially, enabling GPU actor reuse)
- **Timeout**: 300 seconds (increased for large network loading)
- **Redis**: Optional caching (disabled by default)

## Performance Notes

### System Requirements

- **Memory**: ~20GB RAM recommended for 40,000 agents
- **CPU**: Multi-core processor (8+ cores recommended)
- **Disk**: ~5GB for agent populations and logs
- **Network**: Low latency connection if using distributed Ray cluster

### Expected Performance

- **Network loading**: Expect 200-300 seconds for initial network loading (~400,000 edges)
- **LLM requirements**: 40,000 LLM agents will make extensive API calls to Ollama/OpenAI
- **Simulation speed**: Depends on LLM API throughput and system resources
- **Database size**: Grows significantly with simulation length and agent activity

### Optimization Tips

1. **Use PostgreSQL** instead of SQLite for better concurrent write performance
2. **Enable Redis** caching to reduce database load
3. **Adjust `heartbeat_interval`** in simulation configs to balance responsiveness vs. load
4. **Use vLLM** or batched LLM inference for better throughput
5. **Distribute across machines** using Ray cluster for true horizontal scaling

## Monitoring

### Check Client Status

Watch the server logs to see when clients connect:
```bash
tail -f example/llm_4clients_40000/logs/orchestrator_server_server.log
```

### Monitor Individual Clients

Each client's execution log shows its progress:
```bash
tail -f example/llm_4clients_40000/logs/client_1_execution.log
tail -f example/llm_4clients_40000/logs/client_2_execution.log
# etc.
```

### Database Queries

Query the database to see agent activity across all clients:
```bash
sqlite3 example/llm_4clients_40000/simulation_orchestrator_server.db "SELECT COUNT(*) FROM posts;"
```

## Troubleshooting

### Server won't start simulation

- **Issue**: Server is waiting for 4 clients
- **Solution**: Ensure all 4 clients are started and connected
- **Check**: Server logs should show "Client client_N connected" messages

### Network loading timeout

- **Issue**: Network.csv is too large and times out
- **Solution**: Increase `timeout_seconds` in server_config.json to 600 or higher

### LLM errors

- **Issue**: Too many concurrent LLM requests
- **Solution**: 
  - Ensure Ollama is running: `ollama serve`
  - Consider using vLLM for better throughput
  - Reduce `round_actions` in agent populations

### Log file conflicts

- **Issue**: Clients overwriting each other's logs
- **Solution**: Ensure each client has a unique `client_name` in its simulation_config.json
- **Verify**: Check that files have different names (client_1_execution.log, client_2_execution.log, etc.)

### Out of memory

- **Issue**: System runs out of RAM
- **Solution**:
  - Increase system RAM or use swap space
  - Reduce number of agents per client
  - Use distributed Ray cluster across multiple machines

### Clients can't connect to server

- **Issue**: "No server address specified" error
- **Solution**: Update the `server.address` field in all client_N_simulation_config.json files with the Ray address from server startup

## Customization

### Modify Agent Distribution

Edit `generate_population.py` to change:
- Number of agents per client (default: 10,000)
- Number of clients (default: 4)
- Average network degree (default: 10)
- Agent attribute distributions
- Archetype ratios

### Adjust Simulation Parameters

Edit individual `client_N_simulation_config.json` files to:
- Change simulation duration
- Modify discussion topics
- Adjust action likelihoods
- Configure LLM settings differently per client

### Scale to More Clients

To add more clients:
1. Modify `generate_population.py` to generate additional client configs
2. Optionally update `min_to_start` in server_config.json if you need all clients to connect before starting
3. Start the additional clients (sequentially if using `reuse_actors: true`)

## Research Use Cases

This multi-client configuration is ideal for:
- **Horizontal scaling studies**: Measure how simulation scales with distributed clients
- **Large population dynamics**: Study emergent behaviors in 40K+ agent systems
- **Client isolation testing**: Verify that clients don't interfere with each other
- **Load balancing research**: Experiment with different agent distributions
- **Cross-client interaction analysis**: Study how agents from different clients interact
- **System performance benchmarking**: Test infrastructure limits

## See Also

- [llm_population_10000](../llm_population_10000/) - Single client with 10,000 agents
- [mixed_population_10000](../mixed_population_10000/) - Mixed LLM and rule-based agents
- [YSimulator Documentation](../../docs/) - Full documentation
- [Client-Specific Configuration](../CLIENT_SPECIFIC_CONFIG.md) - Advanced client configuration

## Notes

- Each client maintains its own Ray actor pool for agent management
- The shared network topology ensures agents can interact across clients
- Database writes are serialized through the orchestrator server
- Log rotation is automatic (10MB per file, 5 backups, gzip compressed)
- The simulation stops when any client completes its configured duration
