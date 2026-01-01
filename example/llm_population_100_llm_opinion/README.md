# LLM Population 100 with LLM Opinion Evaluation

This example demonstrates a YSimulator configuration with:
- **101 agents total**: **100 LLM-enabled agents** and **1 news page**
- **Initial random social network** with ~1000 follow relationships (~10 connections per agent)
- **Discussion topics**: war, politics, sport, books, movies
- **Dynamic follow actions** using multiple recommendation strategies
- **Agent archetypes**: Validator, Broadcaster, Explorer
- **LLM-based opinion dynamics**: Using the `llm_evaluation` model with neighbor influence

## Opinion Dynamics Configuration

This example uses the **LLM Evaluation Model** for opinion dynamics:
- **Model**: `llm_evaluation` (natural language reasoning)
- **Evaluation Scope**: `neighbors` (considers opinions of followed users)
- **Cold Start**: `neutral` (new opinions start at 0.5)

The LLM evaluates whether agents agree, disagree, or remain neutral about posts by considering:
- Post content
- Author's opinion
- Opinions of agents they follow (neighbors)

This creates more realistic opinion evolution based on social influence and content semantics.

## Agent Distribution

- **1 Page Agent** (`NewsPage`): LLM-enabled news publisher with RSS feed
- **100 LLM Agents**: AI-powered decision making using language models
- **0 Rule-based Agents**: Heuristic-based decision making

## Quick Start

### 1. Generate Configuration

```bash
cd example/llm_population_100_llm_opinion
python generate_population.py
```

This creates:
- `agent_population.json` - Agent definitions
- `network.csv` - Initial social network
- `simulation_config.json` - Simulation parameters
- `server_config.json` - Server settings

### 2. Start Server

```bash
# From repository root
python run_server.py --config example/llm_population_100_llm_opinion/server_config.json
```

### 3. Start Client

```bash
# In a separate terminal
python run_client.py --config example/llm_population_100_llm_opinion/simulation_config.json \
                     --agents example/llm_population_100_llm_opinion/agent_population.json \
                     --prompts example/llm_population_100_llm_opinion/llm_prompts.json
```

## Configuration Files

### agent_population.json
Defines all 101 agents with diverse characteristics:
- Political leanings: left, center, right, neutral
- Activity profiles: Always On, Morning Active, Evening Active
- Professions: Engineer, Teacher, Doctor, Artist, Student
- Content recommendation: random, rchrono, rchrono_followers
- Follow recommendation: random, common_neighbors, jaccard, adamic_adar, preferential_attachment

### network.csv
Initial social network with approximately 1000 directed follow edges using Erdős–Rényi random graph model.

### simulation_config.json
Main simulation parameters:
- Duration: 3 days, 24 slots per day (72 rounds)
- Discussion topics: war, politics, sport, books, movies
- Action likelihoods: post (3.0), comment (5.0), read (2.0), share (1.0), search (5.0), follow (0.1)
- Follow probabilities: 10% daily, 10% secondary after interactions
- **Opinion dynamics**: LLM evaluation model with neighbor influence

### server_config.json
Server settings:
- Database: SQLite (configurable for PostgreSQL/MySQL)
- Timeout: 180 seconds for network loading
- Redis: Optional caching (disabled by default)

## Performance Notes

- **Network loading**: Expect ~1 seconds for initial network loading
- **LLM requirements**: 100 LLM agents will make API calls to Ollama/OpenAI
- **Memory usage**: ~50MB for agent population
- **Database size**: Grows with simulation length and agent activity

## Customization

Edit `generate_population.py` to modify:
- Average network degree (default: 10)
- Agent attribute distributions
- Archetype ratios
- LLM/rule-based split

Edit `simulation_config.json` to adjust:
- Simulation duration
- Discussion topics
- Action likelihoods
- Follow probabilities

## Troubleshooting

### Network not loading
- Check `ysimulator.log` for "Loading social network from network.csv"
- Verify network.csv is in the same directory as simulation_config.json

### LLM errors (if LLM agents present)
- Ensure Ollama is running: `ollama serve`
- Check model availability: `ollama list`
- Verify model name in simulation_config.json

### Performance issues
- Increase `heartbeat_interval` in simulation_config.json
- Reduce `num_days` for shorter simulations
- Consider PostgreSQL for better database performance

## See Also

- [llm_population_100](../llm_population_100/) - 100 LLM agents with bounded confidence opinion model
- [llm_population_1000](../llm_population_1000/) - 1000 LLM agents example
- [mixed_population_100](../mixed_population_100/) - 50/50 mixed agents example
- [Opinion Dynamics Documentation](../../docs/OPINION_DYNAMICS.md) - Full opinion dynamics guide
- [YSimulator Documentation](../../docs/) - Full documentation
