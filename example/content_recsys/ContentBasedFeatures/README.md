# ContentBasedFeatures Example

This example demonstrates the **ContentBasedFeatures** content recommendation system.

## Description

Analyzes attributes of content the user has interacted with (topics, hashtags). Learns preferences from behavior.

## Configuration

- **Population**: 10 agents + 1 news page
- **Duration**: 100 days (2400 rounds)
- **Agent Type**: Rule-based
- **Content RecSys**: ContentBasedFeatures
- **Follow RecSys**: Mixed (random, common_neighbors, jaccard, adamic_adar, preferential_attachment)

## Running the Example

```bash
# Start the server
python run_server.py --config example/content_recsys/ContentBasedFeatures/server_config.json

# In another terminal, start the client
python run_client.py --config example/content_recsys/ContentBasedFeatures/simulation_config.json --population example/content_recsys/ContentBasedFeatures/agent_population.json
```

## Expected Behavior

This recommender system analyzes attributes of content the user has interacted with (topics, hashtags). learns preferences from behavior.

The small population size (10 agents) allows for quick testing and validation of the recommendation algorithm.
