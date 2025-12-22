# Interest Tracking System

The YSimulator now includes a comprehensive interest tracking system that allows agents to have topical preferences that influence their behavior and are learned through interactions.

## Overview

The interest tracking system enables:
- **Agent Interest Configuration**: Define topics of interest for each agent with interaction counts
- **Topic-based Post Generation**: Agents create posts about topics they're interested in
- **Interest Learning**: Agents learn new interests by commenting on posts
- **Temporal Tracking**: All interests are tracked per simulation round for analysis

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
2. **Counts List**: Number of times the agent has interacted with each topic

Topics are weighted by their interaction counts when generating posts.

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

## How It Works

### 1. Agent Registration

When agents are registered:
- Each topic in the agent's interests is saved to the `interests` table (or retrieved if it already exists)
- For each topic, N `user_interest` entries are created (where N is the interaction count)
- All entries are associated with the current round

### 2. Post Generation

When an agent creates a post:
- A topic is randomly sampled from their interests, weighted by interaction counts
- The topic is included in the LLM prompt
- After the post is created, it's associated with the topic in the `post_topics` table

### 3. Comment Learning

When an agent comments on a post:
- The system retrieves all topics associated with the parent post
- For each topic, a new `user_interest` entry is created for the commenting agent
- This represents the agent learning about these topics through engagement

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
```

### Helper Methods

```python
# Validate and extract interests (client/server)
topics, counts = self._validate_and_extract_interests(agent.interests)
```

## Performance Considerations

- Interest lookups use database indexes on `user_id`, `interest_id`, and `round_id`
- Topic names are deduplicated in the `interests` table
- Multiple `user_interest` rows are created to preserve temporal granularity

## Future Enhancements

Potential improvements:
- Interest decay over time
- Topic similarity/clustering
- Interest-based recommendation systems
- Interest strength normalization
- Cross-topic correlations
