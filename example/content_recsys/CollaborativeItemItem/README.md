# CollaborativeItemItem Example

This example demonstrates the **CollaborativeItemItem** content recommendation system.

## Description

Finds posts that are often liked together by the same groups. Uses co-occurrence patterns to recommend related content.

## Configuration

- **Population**: 10 agents + 1 news page
- **Duration**: 100 days (2400 rounds)
- **Agent Type**: Rule-based
- **Content RecSys**: CollaborativeItemItem
- **Follow RecSys**: Mixed (random, common_neighbors, jaccard, adamic_adar, preferential_attachment)

## Running the Example

```bash
# Start the server
python run_server.py --config example/content_recsys/CollaborativeItemItem/server_config.json

# In another terminal, start the client
python run_client.py --config example/content_recsys/CollaborativeItemItem/simulation_config.json --population example/content_recsys/CollaborativeItemItem/agent_population.json
```

## Expected Behavior

This recommender system finds posts that are often liked together by the same groups. uses co-occurrence patterns to recommend related content.

The small population size (10 agents) allows for quick testing and validation of the recommendation algorithm.
