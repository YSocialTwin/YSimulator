# Mixed Population Example with Initial Social Network

This example demonstrates a complete YSimulator configuration with:
- **101 agents total**: 100 regular agents (50 rule-based + 50 LLM-enabled) and 1 news page
- **Initial random social network** with ~1000 follow relationships (~10 connections per agent)
- **Dynamic follow actions** using multiple recommendation strategies
- **Secondary follow behavior** after content interactions
- **Daily follow evaluation** for network growth

## Configuration Files

### agent_population.json
Defines all 101 agents with diverse characteristics:
- **1 Page Agent** (`NewsPage`): LLM-enabled news publisher with RSS feed
- **50 Rule-Based Agents** (`agent_000` to `agent_049`): Deterministic behavior
- **50 LLM Agents** (`agent_050` to `agent_099`): AI-powered decision making

**Agent Attributes:**
- **Archetypes**: Validator (skeptical), Broadcaster (viral), Explorer (curious)
- **Political Leanings**: Left, center, right, neutral
- **Activity Profiles**: Always On, Morning Active, Evening Active
- **Content Recommendation**: `random`, `rchrono`, `rchrono_followers`
- **Follow Recommendation**: `random`, `common_neighbors`, `jaccard`, `adamic_adar`, `preferential_attachment`

### network.csv
Initial social network with approximately 1000 directed follow edges. Each row represents:
```
follower_username,followee_username
```

The network is generated using an Erdős–Rényi random graph model with average degree ~10, creating a realistic starting topology for the simulation.

### simulation_config.json
Main simulation parameters:
- **Duration**: 3 days, 24 slots per day (72 rounds total)
- **Actions Likelihood**: Post (3.0), Comment (5.0), Read (2.0), Share (1.0), Follow (0.5)
- **Follow Probabilities**:
  - `probability_of_daily_follow`: 0.15 (15% chance for active agents at end of day)
  - `probability_of_secondary_follow`: 0.1 (10% chance after read/comment)
- **Reading Behavior**:
  - 60% from followers, 40% from general feed
  - Max thread depth: 5 posts
  - Attention window: 336 rounds (14 days)

### llm_prompts.json
LLM prompts for different agent behaviors:
- **Personas**: Customized for each archetype (Validator, Broadcaster, Explorer)
- **Post Generation**: Authentic content creation
- **Reaction Decisions**: LIKE, COMMENT, or IGNORE
- **Comment Generation**: Contextual responses
- **Follow Decisions**: Primary and secondary follow evaluation

### server_config.json
Server infrastructure settings:
- **Database**: SQLite with Redis caching
- **Ray**: Distributed computing with namespace isolation
- **API**: REST endpoint on port 8000
- **Logging**: INFO level with timestamps

## Usage

### 1. Generate Configuration (Already Done)
```bash
cd example/mixed_population_100
python generate_population.py
```

This creates all necessary JSON and CSV files.

### 2. Start the Server
```bash
# From repository root
python run_server.py --config example/mixed_population_100/server_config.json
```

The server will:
- Initialize Ray cluster
- Set up SQLite database with Redis cache
- Load initial social network from network.csv
- Start REST API on port 8000

### 3. Start the Client
```bash
# In a separate terminal, from repository root
python run_client.py --config example/mixed_population_100/simulation_config.json \
                     --agents example/mixed_population_100/agent_population.json \
                     --prompts example/mixed_population_100/llm_prompts.json
```

The client will:
- Connect to Ray server
- Register all 101 agents
- Load initial network.csv (1000 edges)
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

### Initial Network Loading
On first run, the client:
1. Checks for `network.csv` in config directory
2. Parses ~1000 follow edges
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
- **Rule-based agents**: Randomly decide to follow/unfollow/no_change
- **LLM agents**: Use heuristic (30% follow if new, 10% unfollow if existing)
- Creates additional FOLLOW or UNFOLLOW actions

### Daily Follow Evaluation
At end of each day (15% probability):
- All active agents evaluate new follow opportunities
- Request top-10 suggestions from their `frecsys_type` strategy
- Randomly select one candidate to follow
- Independent of action-based and secondary follows

## Network Evolution

The social network evolves through three mechanisms:

1. **Initial Network** (t=0): ~1000 edges from network.csv
2. **Action-Based Follows** (ongoing): Follow actions with 0.5 likelihood
3. **Secondary Follows** (after interactions): 10% probability after read/comment
4. **Daily Evaluation** (end of day): 15% probability for active agents

**Expected Growth:**
- Day 1: ~1000 → ~1200 edges (20% growth)
- Day 2: ~1200 → ~1450 edges (20% growth)
- Day 3: ~1450 → ~1750 edges (20% growth)

## Agent Behavior Summary

| Agent Type | Count | Behavior | Follow Strategy |
|------------|-------|----------|----------------|
| **Page** | 1 | LLM-generated news posts | Random |
| **Rule-Based** | 50 | Deterministic actions | Various (random, common_neighbors, etc.) |
| **LLM Agents** | 50 | AI-driven decisions | Various (jaccard, adamic_adar, etc.) |

**Archetype Distribution:**
- **Validators** (~33): Skeptical, fact-checking, brief comments
- **Broadcasters** (~33): Viral-focused, high engagement, controversial
- **Explorers** (~34): Curious, question-asking, learning-oriented

## Recommendation Strategies Performance

### Content Recommendation
- `random`: Baseline, uniform selection
- `rchrono`: Recent posts, time-based
- `rchrono_followers`: Recent from followers, social signal

### Follow Recommendation
- `random`: O(1) - Instant selection
- `common_neighbors`: O(n) - Friend-of-friend via JOIN
- `jaccard`: O(n) - Similarity calculation
- `adamic_adar`: O(n²) - Two-step with degree calculation
- `preferential_attachment`: O(n) - Popularity-based COUNT

All strategies use query-based approaches (no NetworkX) for scalability.

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
```

## Customization

### Modify Network Density
Edit `generate_population.py`:
```python
# Line 146: Change avg_degree parameter
edges = generate_random_network(agent_data['agents'], avg_degree=15)  # Denser network
```

### Adjust Follow Probabilities
Edit `simulation_config.json`:
```json
{
  "agents": {
    "probability_of_daily_follow": 0.2,      // 20% daily
    "probability_of_secondary_follow": 0.15  // 15% secondary
  }
}
```

### Change Agent Mix
Edit `generate_population.py`:
```python
# Line 78-80: Adjust split
for i in range(100):
    is_llm = i >= 30  # 30 rule-based, 70 LLM
```

## Troubleshooting

### Network Not Loading
- Check `ysimulator.log` for "Loading social network from network.csv"
- Verify usernames in network.csv match agent_population.json
- Ensure network.csv is in same directory as simulation_config.json

### Database Errors
- Delete `simulation.db` and restart server
- Check Redis is running: `redis-cli ping`
- Verify write permissions in working directory

### LLM Issues
- Ensure Ollama is running: `ollama serve`
- Check model is available: `ollama list`
- Verify model name in simulation_config.json matches installed model

## Next Steps

1. **Analyze Results**: Use SQL queries to explore network evolution
2. **Visualize Network**: Export Follow table and use NetworkX/Gephi
3. **Tune Parameters**: Adjust follow probabilities and observe impact
4. **Extend Simulation**: Increase `num_days` for longer runs
5. **Add Metrics**: Track clustering coefficient, diameter, modularity

## References

- **Network Generation**: Erdős–Rényi random graph (Gilbert's model)
- **Follow Recommendations**: Multiple graph-based strategies with query optimization
- **Agent Archetypes**: Inspired by social media user behavior research
- **Activity Patterns**: Based on real social media usage data
