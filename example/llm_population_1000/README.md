# LLM Population 1000 Example

This example demonstrates a complete YSimulator configuration with:
- **1001 agents total**: 1000 LLM-enabled agents and 1 news page
- **Initial random social network** with ~10,000 follow relationships (~10 connections per agent)
- **Discussion topics**: war, politics, sport, books, movies
- **Dynamic follow actions** using multiple recommendation strategies
- **Secondary follow behavior** after content interactions
- **Daily follow evaluation** for network growth

## Configuration Files

### agent_population.json
Defines all 1001 agents with diverse characteristics:
- **1 Page Agent** (`NewsPage`): LLM-enabled news publisher with RSS feed
- **1000 LLM Agents** (`agent_000` to `agent_999`): AI-powered decision making

**Agent Attributes:**
- **Archetypes**: Validator (skeptical), Broadcaster (viral), Explorer (curious)
- **Political Leanings**: Left, center, right, neutral
- **Activity Profiles**: Always On, Morning Active, Evening Active
- **Content Recommendation**: `random`, `rchrono`, `rchrono_followers`
- **Follow Recommendation**: `random`, `common_neighbors`, `jaccard`, `adamic_adar`, `preferential_attachment`

### network.csv
Initial social network with approximately 10,000 directed follow edges. Each row represents:
```
follower_username,followee_username
```

The network is generated using an Erdős–Rényi random graph model with average degree ~10, creating a realistic starting topology for the simulation.

### simulation_config.json
Main simulation parameters:
- **Duration**: 3 days, 24 slots per day (72 rounds total)
- **Discussion Topics**: ["war", "politics", "sport", "books", "movies"]
- **Actions Likelihood**: Post (3.0), Comment (5.0), Read (2.0), Share (1.0), Search (5.0), Follow (0.1)
- **Follow Probabilities**:
  - `probability_of_daily_follow`: 0.1 (10% chance for active agents at end of day)
  - `probability_of_secondary_follow`: 0.1 (10% chance after read/comment)
- **Reading Behavior**:
  - 60% from followers, 40% from general feed
  - Max thread depth: 5 posts
  - Attention window: 336 rounds (14 days)

### llm_prompts.json
LLM prompts for different agent behaviors (same as mixed_population_100):
- **Personas**: Customized for each archetype (Validator, Broadcaster, Explorer)
- **Post Generation**: Authentic content creation with topic instructions
- **Reaction Decisions**: LIKE, COMMENT, or IGNORE
- **Comment Generation**: Contextual responses
- **Follow Decisions**: Primary and secondary follow evaluation
- **Topic Extraction**: For categorizing articles and posts

### prompts.json
Alternative prompts format with concise templates.

### server_config.json
Server infrastructure settings:
- **Database**: SQLite (can be configured for PostgreSQL or MySQL)
- **Ray**: Distributed computing with namespace isolation
- **Redis**: Optional caching (disabled by default for this large simulation)
- **Logging**: Standard configuration

## Usage

### 1. Generate Configuration (Already Done)
```bash
cd example/llm_population_1000
python generate_population.py
```

This creates all necessary JSON and CSV files.

### 2. Start the Server
```bash
# From repository root
python run_server.py --config example/llm_population_1000/server_config.json
```

The server will:
- Initialize Ray cluster
- Set up SQLite database
- Load initial social network from network.csv
- Wait for clients to connect

### 3. Start the Client
```bash
# In a separate terminal, from repository root
python run_client.py --config example/llm_population_1000/simulation_config.json \
                     --agents example/llm_population_1000/agent_population.json \
                     --prompts example/llm_population_1000/llm_prompts.json
```

The client will:
- Connect to Ray server
- Register all 1001 agents
- Load initial network.csv (~10,000 edges)
- Begin simulation for 3 days

### 4. Monitor Progress
```bash
# Check logs
tail -f ysimulator.log

# Query database (after simulation starts)
sqlite3 simulation.db "SELECT COUNT(*) FROM follow;"
sqlite3 simulation.db "SELECT COUNT(*) FROM post;"
```

## Features Demonstrated

### Large-Scale LLM Simulation
All 1000 agents use LLM for decision-making:
- Post generation based on topics and persona
- Reaction decisions (like, comment, ignore)
- Comment generation in response to posts
- Follow/unfollow decisions based on interactions
- Search behavior for topics of interest

### Discussion Topics
The simulation includes 5 discussion topics:
1. **War** - conflict, military, peace
2. **Politics** - government, policy, elections
3. **Sport** - athletics, teams, competitions
4. **Books** - literature, reading, authors
5. **Movies** - cinema, films, entertainment

Agents may generate posts about these topics, and the LLM can extract topics from content.

### Initial Network Loading
On first run, the client:
1. Checks for `network.csv` in config directory
2. Parses ~10,000 follow edges
3. Validates all usernames exist in agent population
4. Loads edges into Follow table with `action="follow"`
5. Skips loading on subsequent runs (checks database for existing edges)

### Dynamic Follow Actions
Agents can follow users during simulation using their configured `frecsys_type`:
- **Random**: Select any non-following user
- **Common Neighbors**: Friend-of-friend recommendations
- **Jaccard**: Similarity-based suggestions
- **Adamic/Adar**: Link prediction with inverse degree weighting
- **Preferential Attachment**: Follow popular users

### Secondary Follow Behavior
After reading or commenting on posts (10% probability):
- LLM agents use heuristic (30% follow if new, 10% unfollow if existing)
- Creates additional FOLLOW or UNFOLLOW actions

### Daily Follow Evaluation
At end of each day (10% probability):
- All active agents evaluate new follow opportunities
- Request top-10 suggestions from their `frecsys_type` strategy
- Randomly select one candidate to follow
- Independent of action-based and secondary follows

## Network Evolution

The social network evolves through three mechanisms:

1. **Initial Network** (t=0): ~10,000 edges from network.csv
2. **Action-Based Follows** (ongoing): Follow actions with 0.1 likelihood
3. **Secondary Follows** (after interactions): 10% probability after read/comment
4. **Daily Evaluation** (end of day): 10% probability for active agents

**Expected Growth:**
- Day 1: ~10,000 → ~11,500 edges (15% growth)
- Day 2: ~11,500 → ~13,000 edges (13% growth)
- Day 3: ~13,000 → ~14,500 edges (12% growth)

## Agent Behavior Summary

| Agent Type | Count | Behavior | Follow Strategy |
|------------|-------|----------|----------------|
| **Page** | 1 | LLM-generated news posts | Random |
| **LLM Agents** | 1000 | AI-driven decisions | Various (all strategies) |

**Archetype Distribution:**
- **Validators** (~330): Skeptical, fact-checking, brief comments
- **Broadcasters** (~330): Viral-focused, high engagement, controversial
- **Explorers** (~340): Curious, question-asking, learning-oriented

## Performance Considerations

### LLM Requirements
With 1000 LLM agents, expect:
- High LLM API usage (Ollama or OpenAI)
- Longer processing time per round
- Significant memory usage

**Optimization Tips:**
- Use local Ollama for cost efficiency
- Adjust `heartbeat_interval` to allow more time per round
- Consider reducing `num_days` for initial testing
- Monitor system resources during simulation

### Database Performance
SQLite should handle 1000 agents reasonably well for short simulations. For longer runs:
- Consider PostgreSQL for better concurrent access
- Enable Redis caching for improved read performance
- Monitor database file size growth

## Output Files

After simulation completes:
- **simulation.db**: SQLite database with all posts, comments, reactions, follows
- **ysimulator.log**: Client and server logs
- **Ray logs**: In `/tmp/ray/session_*/logs/`

### Query Examples
```sql
-- Total follows over time
SELECT round, COUNT(*) as new_follows 
FROM follow 
WHERE action = 'follow' 
GROUP BY round 
ORDER BY round;

-- Most followed users
SELECT user_id, COUNT(*) as follower_count 
FROM follow 
WHERE action = 'follow' 
GROUP BY user_id 
ORDER BY follower_count DESC 
LIMIT 10;

-- Agent activity
SELECT agent_id, COUNT(*) as post_count 
FROM post 
GROUP BY agent_id 
ORDER BY post_count DESC 
LIMIT 10;

-- Topic distribution in posts
SELECT topic, COUNT(*) as count
FROM post
WHERE topic IS NOT NULL
GROUP BY topic
ORDER BY count DESC;
```

## Customization

### Modify Discussion Topics
Edit `simulation_config.json`:
```json
{
  "simulation": {
    "discussion_topics": ["technology", "science", "art", "music", "food"]
  }
}
```

### Modify Network Density
Edit `generate_population.py`:
```python
# Line ~150: Change avg_degree parameter
edges = generate_random_network(agent_data['agents'], avg_degree=15)  # Denser network
```

### Adjust Follow Probabilities
Edit `simulation_config.json`:
```json
{
  "agents": {
    "probability_of_daily_follow": 0.15,      // 15% daily
    "probability_of_secondary_follow": 0.2    // 20% secondary
  }
}
```

### Change LLM Configuration
Edit `simulation_config.json`:
```json
{
  "llm": {
    "address": "localhost",
    "port": 11434,
    "model": "llama3.2",           // Try different models
    "temperature": 0.9,            // Adjust creativity
    "llm_max_tokens": 100          // Limit response length
  }
}
```

## Troubleshooting

### LLM Issues
- Ensure Ollama is running: `ollama serve`
- Check model is available: `ollama list`
- Verify model name in simulation_config.json matches installed model
- Monitor LLM response times - slow responses will delay simulation

### Network Not Loading
- Check `ysimulator.log` for "Loading social network from network.csv"
- Verify usernames in network.csv match agent_population.json
- Ensure network.csv is in same directory as simulation_config.json

### Database Errors
- Delete `simulation.db` and restart server
- Check write permissions in working directory
- Consider PostgreSQL for better performance with 1000 agents

### Memory Issues
- Reduce `num_days` for shorter simulations
- Adjust `attention_window` to limit memory usage
- Enable Redis caching to reduce database load
- Consider running on a machine with more RAM

### Slow Performance
- Increase `heartbeat_interval` to allow more processing time
- Reduce LLM temperature for faster responses
- Use smaller LLM model (e.g., `llama3.2:1b` instead of larger variants)
- Reduce `round_actions` per agent

## Next Steps

1. **Analyze Results**: Use SQL queries to explore network evolution and content patterns
2. **Visualize Network**: Export Follow table and use NetworkX/Gephi for visualization
3. **Tune Parameters**: Adjust follow probabilities and observe impact on network growth
4. **Extend Simulation**: Increase `num_days` for longer runs (monitor resources)
5. **Add Metrics**: Track clustering coefficient, diameter, modularity, topic trends
6. **Topic Analysis**: Analyze how discussion topics spread through the network
7. **Agent Behavior**: Compare validator vs broadcaster vs explorer behaviors

## References

- **Network Generation**: Erdős–Rényi random graph (Gilbert's model)
- **Follow Recommendations**: Multiple graph-based strategies with query optimization
- **Agent Archetypes**: Inspired by social media user behavior research
- **Activity Patterns**: Based on real social media usage data
- **LLM Integration**: Using local Ollama or OpenAI API for agent decision-making
