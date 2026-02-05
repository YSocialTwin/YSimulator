# ContentBasedVector Example

This example demonstrates the **ContentBasedVector** content recommendation system.

## Description

Recommends posts mathematically close to the user's preference vector. Uses weighted topic distributions for similarity.

## Configuration

- **Population**: 10 agents + 1 news page
- **Duration**: 100 days (2400 rounds)
- **Agent Type**: Rule-based
- **Content RecSys**: ContentBasedVector
- **Follow RecSys**: Mixed (random, common_neighbors, jaccard, adamic_adar, preferential_attachment)

## Running the Example

```bash
# Start the server
python run_server.py --config example/content_recsys/ContentBasedVector/server_config.json

# In another terminal, start the client
python run_client.py --config example/content_recsys/ContentBasedVector/simulation_config.json --population example/content_recsys/ContentBasedVector/agent_population.json
```

## Expected Behavior

This recommender system recommends posts mathematically close to the user's preference vector. uses weighted topic distributions for similarity.

The small population size (10 agents) allows for quick testing and validation of the recommendation algorithm.
