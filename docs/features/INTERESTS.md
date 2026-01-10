# Interest Tracking System

The YSimulator includes a comprehensive interest tracking system that allows agents to have topical preferences that influence their behavior and evolve dynamically through interactions. The system implements a sliding window attention mechanism for realistic interest forgetting.

**Related Documentation**:
- Agent types and profile variables: [AGENT_TYPES.md](../agents/AGENT_TYPES.md#interest-and-opinion-variables)
- Interest-based actions: [AGENT_ACTIONS.md](../agents/AGENT_ACTIONS.md#9-search-search-and-engage-with-content)
- Temporal activities and attention window: [AGENT_TEMPORAL_ACTIVITIES.md](../agents/AGENT_TEMPORAL_ACTIVITIES.md)
- Complete configuration: [CONFIG.md](../configuration/CONFIG.md#agent-behavior-configuration)

## Overview

The interest tracking system enables:
- **Agent Interest Configuration**: Define topics of interest for each agent with interaction counts
- **Topic-based Post Generation**: Agents create posts about topics they're interested in
- **Interest Learning**: Agents learn new interests by commenting on posts
- **Sliding Window Forgetting**: Interests naturally decay as interactions age beyond the attention window
- **Article Topic Extraction**: LLM automatically extracts topics from news articles
- **Temporal Tracking**: All interests are tracked per simulation round for temporal analysis

## Architecture

### Modular Design

Interest management is handled by a dedicated module:

```
YServer/interests_modeling/
├── __init__.py
└── interest_manager.py
```

**InterestManager Class** handles all interest operations:
- Interest validation and extraction
- Topic-to-ID mapping
- Sliding window recomputation
- Article topic storage
- Agent interest state management

**Server Delegation**: The OrchestratorServer delegates all interest operations to InterestManager for better modularity and separation of concerns.

## Configuration

### Agent Population Configuration

In your `agent_population.json` file, you can specify interests for each agent using the following format:

```json
{
  "agents": [
    {
      "id": "agent-uuid-here",
      "username": "TechEnthusiast",
      "interests": [
        ["Technology", "AI", "Programming"],
        [5, 3, 2]
      ],
      ...
    }
  ]
}
```

The `interests` field is optional and consists of two lists:
1. **Topics List**: Names of the topics the agent is interested in
2. **Counts List**: Number of times the agent has interacted with each topic (within the attention window)

Topics are weighted by their interaction counts when generating posts.

### Attention Window Configuration

Configure the forgetting mechanism in `simulation_config.json`:

```json
{
  "agents": {
    "attention_window": 336
  }
}
```

The `attention_window` (default: 336 rounds = 14 days at 24 slots/day) determines how far back to look when computing interest counts. As entries fall outside this window, interest counts decrease naturally.

### LLM Prompt Configuration

The system uses a `{topic_instruction}` placeholder in the post generation prompt template. Update your `llm_prompts.json`:

```json
{
  "generate_post": {
    "system_template": "{persona}",
    "user_template": "Write a tweet for Day {day} Slot {slot}.{topic_instruction} Max 15 words."
  }
}
```

When a topic is selected, `{topic_instruction}` is replaced with " Topic: [TopicName].". If no topic is available, it's replaced with an empty string.

### Article Topic Extraction Configuration

Configure the LLM prompt for extracting topics from articles:

```json
{
  "extract_article_topics": {
    "system_template": "You are a topic extraction assistant. Extract exactly 1 or 2 main topics from the article. Return ONLY the topics, separated by commas, no other text.",
    "user_template": "Extract 1-2 main topics from this article:\n\n{article_text}\n\nTopics (comma-separated):"
  }
}
```

## How It Works

### 1. Agent Registration

When agents are registered:
- Each topic in the agent's interests is saved to the `interests` table (or retrieved if it already exists)
- For each topic, N `user_interest` entries are created (where N is the interaction count)
- All entries are associated with the current round
- InterestManager maintains an in-memory copy for fast access

### 2. Post Generation

When an agent creates a post:
- A topic is randomly sampled from their interests, weighted by interaction counts
- The topic is included in the LLM prompt
- After the post is created, it's associated with the topic in the `post_topics` table
- A `user_interest` entry is created for this interaction

### 3. Comment Learning

When an agent comments on a post:
- The system retrieves all topics associated with the parent post
- For each topic, a new `user_interest` entry is created for the commenting agent
- This represents the agent learning about these topics through engagement

### 4. Sliding Window Forgetting

At the end of each day:
- InterestManager recomputes all agent interests based on the attention window
- Only `user_interest` entries within the window are counted
- Topics with count 0 are automatically removed
- This creates realistic interest decay over time

### 5. Article Topic Extraction

When page agents post articles:
- Client checks if article already has topics (avoids duplicate extraction)
- If not, client uses LLM to extract 1-2 main topics from title and summary
- Topics are stored in `interests` table and linked via `article_topics`
- When post is created, topics are automatically linked to `post_topics`

## Database Schema

### Tables Used

**interests**
- `iid` (UUID): Unique interest identifier
- `interest` (Text): Topic name

**user_interest**
- `id` (UUID): Record identifier
- `user_id` (UUID): Agent who has this interest
- `interest_id` (UUID): Reference to the interest
- `round_id` (UUID): When this interest was recorded

**post_topics**
- `id` (UUID): Record identifier
- `post_id` (UUID): The post
- `topic_id` (UUID): The topic associated with the post

**article_topics**
- `id` (UUID): Record identifier
- `article_id` (UUID): The article
- `topic_id` (UUID): The topic extracted from the article

## Backward Compatibility

All interest tracking features are optional:
- Agents without an `interests` field work normally
- Posts without topics are created as before
- The system gracefully handles missing or malformed interest data

## Example Use Cases

### Research Questions

The interest tracking system enables analysis of:
- How agent interests evolve over time
- Topic-based community formation
- Interest propagation through the network
- Influence of topics on engagement patterns
- Interest decay and forgetting patterns
- Article topic distribution and trends

### Configuration Examples

**News Organization:**
```json
"interests": [
  ["Breaking News", "Politics", "World Events"],
  [10, 8, 7]
]
```

**Tech Influencer:**
```json
"interests": [
  ["AI", "Startups", "Innovation", "Tech Trends"],
  [15, 10, 8, 5]
]
```

**General User:**
```json
"interests": [
  ["Sports", "Entertainment"],
  [3, 2]
]
```

## Validation

The system validates interest data:
- Must be a list/tuple with exactly 2 elements
- First element must be a list of topic names (strings)
- Second element must be a list of counts (integers)
- Both lists must have the same length (or counts can be shorter)

Invalid interest data is silently ignored, and the agent operates without interests.

## API

### InterestManager Methods

```python
# Initialize interest manager (done by server)
interest_manager = InterestManager(service layer, attention_window=336)

# Validate and extract interests
topics, counts = interest_manager.validate_and_extract_interests(agent.interests)

# Initialize agent interests during registration
interest_manager.initialize_agent_interests(agent_id, interests, round_id)

# Recompute single agent interests (sliding window)
interest_manager.recompute_agent_interests_from_window(agent_id)

# Recompute all agent interests (end of day)
interest_manager.recompute_all_agent_interests(agent_ids)

# Get current interest state
agent_interests = interest_manager.get_agent_interests()

# Article topic operations
topic_ids = interest_manager.get_article_topics(article_id)
topic_ids = interest_manager.store_article_topics(article_id, topic_names)
```

### Server Delegation Methods

```python
# Server delegates to InterestManager
server._validate_and_extract_interests(interests)
server._recompute_agent_interests_from_window(agent_id)
server._recompute_all_agent_interests()
server.get_updated_agent_interests()
server.get_article_topics(article_id)
server.store_article_topics(article_id, topic_names)
```

### Database Methods

```python
# Add or retrieve an interest
interest_id = db.add_or_get_interest("Technology")

# Record a user interest
db.add_user_interest(user_id, interest_id, round_id)

# Associate a post with a topic
db.add_post_topic(post_id, topic_id)

# Get all topics for a post
topic_ids = db.get_post_topics(post_id)

# Get interests within attention window
interests = db.get_user_interests_in_window(user_id, current_round_id, attention_window)

# Count interests within window
counts = db.compute_interest_counts_in_window(user_id, current_round_id, attention_window)
```

## Performance Considerations

- Interest lookups use database indexes on `user_id`, `interest_id`, and `round_id`
- Topic names are deduplicated in the `interests` table
- Multiple `user_interest` rows preserve temporal granularity
- In-memory caching of agent interests for fast access
- Sliding window queries optimized for range-based filtering

## Implementation Notes

### Sliding Window Mechanism

The attention window creates realistic forgetting:
- Configured in rounds (e.g., 336 rounds = 14 days at 24 slots/day)
- Query filters: `(day, hour) >= (cutoff_day, cutoff_hour)`
- Only entries within window count toward interest scores
- Topics with count 0 are automatically removed
- Daily recomputation ensures accurate state

### Client-Server Separation

- **Client**: Owns LLM service, extracts article topics
- **Server**: Persists topics to database via InterestManager
- Clean separation prevents Ray handle passing issues
- Better testability and maintainability

### Temporal Tracking

Multiple `user_interest` entries per topic maintain:
- Historical interaction patterns
- Precise temporal analysis capabilities
- Support for future decay algorithms
- Compatibility with sliding window mechanism

---

## Related Documentation

- **[AGENT_ACTIONS.md](../agents/AGENT_ACTIONS.md)**: Interest-based posting and search actions
- **[AGENT_TYPES.md](../agents/AGENT_TYPES.md)**: Agent profile variables including interests field
- **[AGENT_TEMPORAL_ACTIVITIES.md](../agents/AGENT_TEMPORAL_ACTIVITIES.md)**: Attention window and temporal recomputation
- **[OPINION_DYNAMICS.md](OPINION_DYNAMICS.md)**: Opinion tracking (complementary to interests)
- **[CONFIG.md](../configuration/CONFIG.md)**: Complete configuration reference
- **[ARCHITECTURE.md](../architecture/ARCHITECTURE.md)**: InterestManager architecture

---

**Last Updated**: January 2, 2026  
**Version**: 2.0
