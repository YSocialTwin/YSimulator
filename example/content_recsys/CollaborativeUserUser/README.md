# CollaborativeUserUser Example

This example demonstrates the **CollaborativeUserUser** content recommendation system.

## Description

Finds users with high overlap in liked posts and recommends posts they liked. Uses behavioral similarity (actual likes) to identify similar users.

## Configuration

- **Population**: 10 agents + 1 news page
- **Duration**: 100 days (2400 rounds)
- **Agent Type**: Rule-based
- **Content RecSys**: CollaborativeUserUser
- **Follow RecSys**: Mixed (random, common_neighbors, jaccard, adamic_adar, preferential_attachment)

## Running the Example

```bash
# Start the server
python run_server.py --config example/content_recsys/CollaborativeUserUser/server_config.json

# In another terminal, start the client
python run_client.py --config example/content_recsys/CollaborativeUserUser/simulation_config.json --population example/content_recsys/CollaborativeUserUser/agent_population.json
```

## Expected Behavior

This recommender system finds users with high overlap in liked posts and recommends posts they liked. uses behavioral similarity (actual likes) to identify similar users.

The small population size (10 agents) allows for quick testing and validation of the recommendation algorithm.
