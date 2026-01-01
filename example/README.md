# YSimulator Examples

This directory contains various pre-configured population examples for running YSimulator with different scales and agent compositions.

## Population Examples

### LLM-Only Populations
All agents use Large Language Models for decision-making. Best for testing advanced AI behaviors and interactions.

| Example | Total Agents | LLM Agents | Rule-based | Network Size | Opinion Model |
|---------|--------------|------------|------------|--------------|---------------|
| [llm_population_100](llm_population_100/) | 101 | 100 + 1 page | 0 | ~1,000 edges | Bounded Confidence |
| [llm_population_100_llm_opinion](llm_population_100_llm_opinion/) | 101 | 100 + 1 page | 0 | ~1,000 edges | **LLM Evaluation** |
| [llm_population_100_no_opinion](llm_population_100_no_opinion/) | 101 | 100 + 1 page | 0 | ~1,000 edges | **Disabled** |
| [llm_population_1000](llm_population_1000/) | 1001 | 1000 + 1 page | 0 | ~10,000 edges | Bounded Confidence |
| [llm_population_5000](llm_population_5000/) | 5001 | 5000 + 1 page | 0 | ~50,000 edges | Bounded Confidence |
| [llm_population_10000](llm_population_10000/) | 10001 | 10000 + 1 page | 0 | ~100,000 edges | Bounded Confidence |

**Use cases:**
- Research on LLM-driven social dynamics
- Testing advanced AI reasoning and interactions
- Studying emergent behaviors in AI populations
- **llm_population_100_llm_opinion**: Testing LLM-based opinion evaluation with social influence
- **llm_population_100_no_opinion**: Baseline simulations without opinion dynamics
- Requires: Ollama or OpenAI API access

### Mixed Populations
50% LLM agents, 50% rule-based agents. Balanced approach for cost-effective simulations with diverse behaviors.

| Example | Total Agents | LLM Agents | Rule-based | Network Size |
|---------|--------------|------------|------------|--------------|
| [mixed_population_100](mixed_population_100/) | 101 | 50 + 1 page | 50 | ~1,000 edges |
| [mixed_population_1000](mixed_population_1000/) | 1001 | 500 + 1 page | 500 | ~10,000 edges |
| [mixed_population_5000](mixed_population_5000/) | 5001 | 2500 + 1 page | 2500 | ~50,000 edges |
| [mixed_population_10000](mixed_population_10000/) | 10001 | 5000 + 1 page | 5000 | ~100,000 edges |

**Use cases:**
- Comparing LLM vs rule-based behaviors
- Cost-effective large-scale simulations
- Testing hybrid agent ecosystems
- Studying influence patterns between different agent types

### Rule-Based Populations
All agents use deterministic rule-based decision-making. Fastest and most predictable simulations.

| Example | Total Agents | LLM Agents | Rule-based | Network Size |
|---------|--------------|------------|------------|--------------|
| [rule_population_100](rule_population_100/) | 101 | 1 page | 100 | ~1,000 edges |
| [rule_population_1000](rule_population_1000/) | 1001 | 1 page | 1000 | ~10,000 edges |
| [rule_population_5000](rule_population_5000/) | 5001 | 1 page | 5000 | ~50,000 edges |
| [rule_population_10000](rule_population_10000/) | 10001 | 1 page | 10000 | ~100,000 edges |

**Use cases:**
- Testing platform performance and scalability
- Fast baseline simulations
- Development and debugging
- No LLM infrastructure required

## Quick Start

### 1. Choose a Population

Select an example based on your needs:
- **Small (100-1000 agents)**: Quick testing and development
- **Medium (5000 agents)**: Research and experiments
- **Large (10000 agents)**: Large-scale studies (requires significant resources)

### 2. Start the Server

```bash
# From repository root
python run_server.py --config example/<population_name>/server_config.json
```

Example:
```bash
python run_server.py --config example/mixed_population_1000/server_config.json
```

### 3. Start the Client

```bash
# In a separate terminal
python run_client.py --config example/<population_name>/simulation_config.json \
                     --agents example/<population_name>/agent_population.json \
                     --prompts example/<population_name>/llm_prompts.json  # or prompts.json for rule-based
```

Example:
```bash
python run_client.py --config example/mixed_population_1000/simulation_config.json \
                     --agents example/mixed_population_1000/agent_population.json \
                     --prompts example/mixed_population_1000/llm_prompts.json
```

## Each Example Contains

Every population example includes these files:

- **agent_population.json** - Agent definitions with attributes (age, profession, archetype, etc.)
- **network.csv** - Initial social network with ~10 connections per agent
- **simulation_config.json** - Simulation parameters (duration, topics, actions)
- **server_config.json** - Server settings (database, timeout, Redis)
- **generate_population.py** - Script to regenerate the population
- **README.md** - Detailed documentation for the example
- **llm_prompts.json** - LLM prompts (for LLM-enabled populations)
- **prompts.json** - Rule-based prompts (for rule-based agents)

## Customizing Examples

### Regenerate a Population

Each example includes a `generate_population.py` script:

```bash
cd example/<population_name>
python generate_population.py
```

This will regenerate all configuration files with new random seeds and network structures.

### Modify Agent Distribution

Edit the `generate_population.py` script in any example to customize:
- Number of agents
- LLM vs rule-based ratio
- Network density (avg_degree parameter)
- Agent attributes (age, profession, archetype)
- Activity profiles
- Recommendation strategies

### Adjust Simulation Parameters

Edit `simulation_config.json` to change:
- **num_days**: Simulation duration (3 days default)
- **discussion_topics**: Topics agents discuss (war, politics, sport, books, movies)
- **actions_likelihood**: Probability of different actions (post, comment, share, etc.)
- **probability_of_daily_follow**: Chance of following someone each day (10% default)
- **heartbeat_interval**: Time between simulation rounds (5 seconds default)

## Common Configurations

### Legacy Examples (in root directory)

These files provide backward compatibility with older YSimulator versions:

- **agent_population.json** - Small example population (deprecated, use specific examples instead)
- **agent_population_small.json** - Minimal population for testing
- **agent_population_full.json** - Large population (deprecated)
- **simulation_config.json** - Basic simulation config
- **server_config.json** - Basic server config
- **llm_prompts.json** - LLM prompts for agent decision-making
- **prompts.json** - Rule-based prompts

**Recommendation**: Use the organized population examples (llm_population_*, mixed_population_*, rule_population_*) instead of these legacy files for better clarity and documentation.

## Performance Considerations

### Small Populations (100-1000 agents)
- **Memory**: ~100-500MB
- **LLM calls**: Hundreds per round (for LLM populations)
- **Suitable for**: Laptops, development, quick testing

### Medium Populations (5000 agents)
- **Memory**: ~2-3GB
- **LLM calls**: Thousands per round (for LLM populations)
- **Network loading**: ~30-60 seconds
- **Suitable for**: Workstations, research experiments

### Large Populations (10000 agents)
- **Memory**: ~5-8GB
- **LLM calls**: Tens of thousands per round (for LLM populations)
- **Network loading**: ~60-120 seconds
- **Suitable for**: Servers, large-scale studies
- **Recommendations**: 
  - Use PostgreSQL instead of SQLite
  - Enable Redis caching
  - Consider rule-based or mixed populations to reduce LLM costs

## LLM Requirements

### For LLM-Enabled Populations

**Local Setup (Recommended):**
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull llama3.2

# Verify it's running
ollama list
```

**OpenAI API:**
Edit `simulation_config.json`:
```json
{
  "llm": {
    "address": "api.openai.com",
    "model": "gpt-3.5-turbo",
    "llm_api_key": "your-api-key-here"
  }
}
```

**Cost Estimates (OpenAI):**
- 100 LLM agents: ~$0.50-1.00 per simulated day
- 1000 LLM agents: ~$5-10 per simulated day
- 10000 LLM agents: ~$50-100 per simulated day

Use rule-based or mixed populations to reduce costs.

## Network Structure

All examples use an **Erdős–Rényi random graph** for the initial social network:
- Average degree: ~10 connections per agent
- Directed edges (follower → followee)
- Stored in `network.csv`

The network evolves during simulation through:
- Action-based follows (follow action with 0.1 likelihood)
- Secondary follows after interactions (10% probability)
- Daily follow evaluations (10% probability)

## Discussion Topics

All simulations include these discussion topics by default:
1. **war** - Conflict, military, peace
2. **politics** - Government, policy, elections
3. **sport** - Athletics, teams, competitions
4. **books** - Literature, reading, authors
5. **movies** - Cinema, films, entertainment

Topics can be customized in `simulation_config.json`.

## Agent Archetypes

Three behavioral archetypes distributed equally across all populations:

1. **Validators (33%)**: Skeptical, fact-checking, brief comments
2. **Broadcasters (33%)**: Viral-focused, high engagement, controversial
3. **Explorers (34%)**: Curious, question-asking, learning-oriented

Archetype behavior is defined in the LLM prompts and affects how agents post, comment, and interact.

## Troubleshooting

### Network Loading Issues
```bash
# Check if network.csv exists
ls -lh example/<population_name>/network.csv

# Verify network matches agent population
head -5 example/<population_name>/network.csv
```

### LLM Connection Issues
```bash
# Test Ollama
curl http://localhost:11434/api/tags

# Check model availability
ollama list
```

### Memory Issues
- Start with smaller populations (100-1000 agents)
- Use rule-based populations to reduce memory
- Increase system swap space
- Consider a machine with more RAM

### Slow Performance
- Increase `heartbeat_interval` in simulation_config.json
- Reduce `num_days` for shorter simulations
- Use faster LLM models (e.g., llama3.2:1b)
- Use rule-based populations

## Database Setup

### SQLite (Default)
No setup required. Database file created automatically.

### PostgreSQL (Recommended for large simulations)
```bash
# Install PostgreSQL
sudo apt install postgresql

# Create database
sudo -u postgres createdb ysimulator

# Update server_config.json
{
  "database": {
    "type": "postgresql",
    "postgresql": {
      "host": "localhost",
      "database": "ysimulator",
      "username": "postgres",
      "password": "your-password"
    }
  }
}
```

### MySQL
```bash
# Install MySQL
sudo apt install mysql-server

# Create database
mysql -u root -p -e "CREATE DATABASE ysimulator;"

# Update server_config.json
{
  "database": {
    "type": "mysql",
    "mysql": {
      "host": "localhost",
      "database": "ysimulator",
      "username": "root",
      "password": "your-password"
    }
  }
}
```

## Generating Custom Populations

Use the `scripts/generate_all_populations.py` script to create custom population sets:

```bash
# Generate all standard populations
python scripts/generate_all_populations.py
```

Or modify an existing `generate_population.py` to create custom variants with different:
- Population sizes
- LLM/rule-based ratios
- Network structures
- Agent distributions

## Support

For issues, questions, or contributions:
- GitHub Issues: https://github.com/YSocialTwin/YSimulator/issues
- Documentation: See repository README.md
- Examples: Each population example has detailed README.md

## License

All examples are part of YSimulator and follow the same license as the main project.
