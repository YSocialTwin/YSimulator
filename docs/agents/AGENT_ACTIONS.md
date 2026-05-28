# Agent Actions in YSimulator

This document provides a comprehensive reference for all available agent actions in YSimulator, including their implementation details, parameters, and usage patterns.

## Table of Contents
- [Overview](#overview)
- [Action Architecture](#action-architecture)
- [Available Actions](#available-actions)
- [Action Selection Mechanism](#action-selection-mechanism)
- [Implementation Details](#implementation-details)
- [Configuration](#configuration)

---

## Overview

YSimulator agents can perform various social media actions during each simulation time slot. Actions are the fundamental units of agent behavior and represent all possible interactions in the simulated social media environment.

### Action Categories

1. **Content Creation**: Creating original posts, sharing news, sharing images
2. **Content Interaction**: Reading, reacting (like, love, laugh, angry, sad), commenting
3. **Content Distribution**: Sharing/reposting content
4. **Network Actions**: Following/unfollowing users, including reciprocal follow-back and unfollow-back
5. **Discovery Actions**: Searching for content by topic

### Dual Implementation Approach

Each action type has two implementations:
- **LLM-based**: Uses language models for intelligent, contextual behavior
- **Rule-based**: Uses simple deterministic logic for cost-effective simulation

See [AGENT_TYPES.md](AGENT_TYPES.md) for details on how agents choose between implementations.

---

## Action Architecture

### Action Data Transfer Object (ActionDTO)

All actions are represented using the `ActionDTO` dataclass:

```python
@dataclass
class ActionDTO:
    agent_id: str              # UUID of the agent performing action
    cluster_id: int            # Agent's cluster (determines persona)
    action_type: str           # Type: POST, LIKE, COMMENT, SHARE, FOLLOW, UNFOLLOW
    content: str = None        # Text content for posts/comments
    target_post_id: str = None # UUID of target post (for reactions/comments/shares)
    article_id: str = None     # UUID of news article (for news posts)
    target_user_id: str = None # UUID of target user (for follow/unfollow)
    topic: str = None          # Topic name for posts
    annotations: dict = None   # Text annotations (hashtags, mentions, sentiment)
    updated_opinions: dict = None  # Opinion updates (for comment actions)
```

### Action Flow

```
Agent Decision → Action Generation → Text Annotation → Server Submission → Database Storage
```

1. **Decision Phase**: Agent decides which action to perform based on archetype and likelihood configuration
2. **Generation Phase**: Action is generated using LLM or rule-based implementation
3. **Annotation Phase**: Text content is analyzed for hashtags, mentions, sentiment, toxicity
4. **Submission Phase**: Action is sent to server via Ray remote call
5. **Storage Phase**: Server stores action in database (SQL and optionally Redis)

Reciprocal follow decisions are applied immediately after successful follow or unfollow actions. The client evaluates whether the reverse edge should be created or removed, and the server validates current graph state before persisting the reciprocal action.

---

## Available Actions

### 1. POST (Create Original Content)

Create an original social media post.

#### LLM Implementation

**Function**: `generate_llm_post_async(llm_handle, cluster_id, day, slot, agent_attrs)`

**Behavior**:
- Uses LLM to generate contextual, varied content
- Considers agent persona (cluster_id)
- Adapts to simulation time (day, slot)
- Incorporates agent attributes (name, age, demographics)
- May include topics from agent's interests

**Returns**: Ray ObjectRef (future) resolving to post content (str)

**Example Output**:
```
"Just finished reading about AI advances. Fascinating how quickly things are moving! #AI #Technology"
```

#### Rule-Based Implementation

**Function**: `generate_rule_based_post(agent_id, cluster_id)`

**Behavior**:
- Creates simple template-based content
- Uses cluster ID in content
- Deterministic and predictable

**Returns**: ActionDTO with action_type="POST"

**Example Output**:
```
"Cluster 1 post"
```

#### Configuration

```json
{
  "simulation": {
    "actions_likelihood": {
      "post": 3.0
    }
  }
}
```

**Related Documentation**:
- Interest-based posting: [INTERESTS.md](../features/INTERESTS.md)
- Opinion dynamics in posts: [OPINION_DYNAMICS.md](../features/OPINION_DYNAMICS.md)

---

### 2. COMMENT (Comment on Post)

Create a comment or reply on an existing post.

#### LLM Implementation

**Function**: `generate_llm_reply_to_mention_async(llm_handle, cluster_id, post_content, agent_attrs, author_name, thread_context)`

**Behavior**:
- Generates contextual replies based on post content
- Considers thread context (previous comments)
- References original author by username
- Adapts style to agent persona
- Can update agent opinions based on interaction (if opinion dynamics enabled)

**Returns**: Ray ObjectRef resolving to comment text (str)

**Example Output**:
```
"@alice Great point about climate change! I've been thinking about this too. #sustainability"
```

#### Rule-Based Implementation

**Function**: `generate_rule_based_comment(agent_id, cluster_id, target_post_id)`

**Behavior**:
- Creates simple "COMMENT" text
- For mentions: `generate_rule_based_reply_to_mention()` adds @username prefix

**Returns**: ActionDTO with action_type="COMMENT"

**Example Output**:
```
"COMMENT"
"@alice COMMENT"  # For replies to mentions
```

#### Configuration

```json
{
  "simulation": {
    "actions_likelihood": {
      "comment": 5.0
    }
  }
}
```

**Related Documentation**:
- Opinion evolution via comments: [OPINION_DYNAMICS.md](../features/OPINION_DYNAMICS.md)
- Interest learning via comments: [INTERESTS.md](../features/INTERESTS.md)

---

### 3. READ (Discover and React to Content)

Discover posts via recommendation system and react to them.

#### LLM Implementation

**Function**: `generate_llm_read_async(llm_handle, cluster_id, content, agent_attrs)`

**Behavior**:
- LLM evaluates post content
- Decides reaction type based on persona
- Can choose: LIKE, LOVE, LAUGH, ANGRY, SAD, COMMENT, IGNORE

**Returns**: Ray ObjectRef resolving to reaction type (str)

**Possible Outputs**: LIKE, LOVE, LAUGH, ANGRY, SAD, COMMENT, IGNORE

#### Rule-Based Implementation

**Function**: `generate_rule_based_read(agent_id, cluster_id, target_post_id)`

**Behavior**:
- Randomly chooses: LIKE, ANGRY (represents dislike), or IGNORE
- Equal probability for each option
- Returns None for IGNORE

**Returns**: ActionDTO with reaction type, or None for IGNORE

**Reaction Types**:
- LIKE: Positive reaction
- ANGRY: Negative reaction (represents dislike)
- IGNORE: No action

#### Configuration

```json
{
  "simulation": {
    "actions_likelihood": {
      "read": 2.0
    }
  },
  "agents": {
    "reading_from_follower_ratio": 0.6,
    "max_length_thread_reading": 5
  }
}
```

**Related Documentation**:
- Content recommendation: [RECOMMENDATION_SYSTEMS.md](../features/RECOMMENDATION_SYSTEMS.md)
- Secondary follow after read: [ARCHITECTURE.md](../architecture/ARCHITECTURE.md#secondary-follow-mechanism)

---

### 4. SHARE (Repost Content)

Share or repost existing content to your followers.

#### LLM Implementation

**Behavior**:
- LLM agents can share when triggered by search action
- Generate contextual sharing commentary

#### Rule-Based Implementation

**Function**: `generate_rule_based_share(agent_id, cluster_id, target_post_id)`

**Behavior**:
- Creates simple sharing text with cluster ID
- Always includes target_post_id reference

**Returns**: ActionDTO with action_type="SHARE"

**Example Output**:
```
"Sharing from cluster 1"
```

#### Configuration

```json
{
  "simulation": {
    "actions_likelihood": {
      "share": 1.0
    }
  }
}
```

**Archetype Availability**: Validators and Broadcasters (not Explorers by default)

---

### 5. FOLLOW (Follow User)

Establish a follow relationship with another user.

#### LLM Implementation

**Function**: `generate_llm_follow_async(llm_handle, cluster_id, candidate_users)`

**Behavior**:
- LLM evaluates list of candidate users
- Makes informed decision about who to follow
- Can choose not to follow anyone

**Returns**: Ray ObjectRef resolving to user_id (str) or None

#### Rule-Based Implementation

**Function**: `generate_rule_based_follow(agent_id, cluster_id, target_user_id)`

**Behavior**:
- Always follows the suggested user
- No decision-making logic

**Returns**: ActionDTO with action_type="FOLLOW"

#### Follow Mechanisms

YSimulator supports three ways agents establish follow relationships:

1. **Primary Follow Action**: Explicit FOLLOW action in action_likelihood
2. **Daily Follow Evaluation**: End-of-day follow suggestions (see [AGENT_TEMPORAL_ACTIVITIES.md](AGENT_TEMPORAL_ACTIVITIES.md))
3. **Secondary Follow**: After reading/commenting on posts (see [ARCHITECTURE.md](../architecture/ARCHITECTURE.md#secondary-follow-mechanism))

#### Time-Based Follow Action Decay

Primary follow actions (mechanism 1 above) can be configured to decay over time, modeling the realistic behavior where users are most active in following others during their initial period of platform activity.

**Configuration:**

```json
{
  "agents": {
    "follow_action_decay": {
      "enabled": true,
      "decay_function": "exponential",
      "half_life_rounds": 168,
      "decay_rate": 0.01,
      "min_probability_ratio": 0.1
    }
  }
}
```

**Behavior:**
- When enabled, the probability of selecting the FOLLOW action decreases as a function of rounds since the agent joined the simulation
- All agents (both initial and dynamically added) are affected by decay
- When agents are first registered, they receive a `joined_on` timestamp
- Initial agents get `joined_on` set to the round when simulation starts
- New agents get `joined_on` set to the round when they join
- Two decay functions available:
  - **Exponential**: `multiplier = 0.5 ^ (rounds_since_join / half_life_rounds)`
  - **Linear**: `multiplier = 1.0 - (decay_rate × rounds_since_join)`
- The decay multiplier is applied to the follow action weight in `actions_likelihood`
- Multiplier never goes below `min_probability_ratio` (default: 0.1)

**Example:**
With exponential decay and half_life_rounds=168 (7 days × 24 slots):
- Day 0 (join): 100% follow probability
- Day 7: 50% follow probability
- Day 14: 25% follow probability
- Day 21: 12.5% follow probability (but clamped to min_probability_ratio if below 10%)

**Notes:**
- Decay only applies to primary follow actions selected during normal action selection
- Daily follow evaluation and secondary follows are not affected by this decay
- See [CONFIG.md](../configuration/CONFIG.md#follow-action-decay-configuration) for detailed configuration options

#### Configuration

```json
{
  "simulation": {
    "actions_likelihood": {
      "follow": 0.1
    }
  },
  "agents": {
    "probability_of_daily_follow": 0.1,
    "probability_of_secondary_follow": 0.3,
    "follow_action_decay": {
      "enabled": false,
      "decay_function": "exponential",
      "half_life_rounds": 168,
      "min_probability_ratio": 0.1
    }
  }
}
```

**Related Documentation**:
- Follow recommendation algorithms: [RECOMMENDATION_SYSTEMS.md](../features/RECOMMENDATION_SYSTEMS.md#follow-recommendation-system)
- Network dynamics: [ARCHITECTURE.md](../architecture/ARCHITECTURE.md#dynamic-social-network)

---

### 6. UNFOLLOW (Unfollow User)

Break a follow relationship with another user.

#### Implementation

**Function**: ActionDTO with action_type="UNFOLLOW"

**Behavior**:
- Created during secondary follow evaluation
- LLM agents: 10% chance to unfollow when already following
- Rule-based agents: Random decision (equal probabilities for follow/unfollow/no_change)

**Trigger Conditions**:
- After reading or commenting on a post
- Evaluated with `probability_of_secondary_follow`

#### Configuration

```json
{
  "agents": {
    "probability_of_secondary_follow": 0.3
  }
}
```

**Related Documentation**: [ARCHITECTURE.md](../architecture/ARCHITECTURE.md#secondary-follow-mechanism)

---

### 7. IMAGE (Share Image with Commentary)

Share an image from RSS feeds with personalized commentary.

#### LLM Implementation

**Function**: `generate_image_post_async(server, llm_service, agent_cluster, image_data, topics, agent_attrs)`

**Behavior**:
- Uses vision LLM (llm_v) to describe image
- Uses text LLM to generate social media commentary about the image
- Incorporates related topics from article
- Creates engaging post text (max 280 characters)

**Returns**: Tuple of (Ray ObjectRef for commentary, image_id)

**Requirements**:
- Vision LLM (llm_v) must be configured
- Image must exist in database (from RSS feed with images)

**Example Output**:
```
"This visualization perfectly captures the essence of data science! Love how it breaks down complex concepts. #DataScience #Visualization"
```

#### Rule-Based Implementation

**Function**: `generate_rule_based_image_post(agent_id, cluster_id, image_id)`

**Behavior**:
- Creates simple "IMAGE" text
- References image via image_id

**Returns**: ActionDTO with action_type="POST" and content="IMAGE"

#### Configuration

```json
{
  "simulation": {
    "actions_likelihood": {
      "image": 0.5
    }
  },
  "llm_v": {
    "address": "localhost",
    "port": 11434,
    "model": "minicpm-v",
    "temperature": 0.5
  }
}
```

**Note**: Set image: 0.0 to disable if no vision LLM is available.

**Related Documentation**: [CONFIG.md](../configuration/CONFIG.md#vision-llm-configuration)

---

### 8. NEWS (Share News Article)

Share news articles from RSS feeds (page agents only).

#### LLM Implementation

**Function**: `generate_news_post_async(news_service, llm_service, agent_cluster, article, website_name)`

**Behavior**:
- Saves article to database
- Generates LLM commentary on the article
- Creates engaging post with perspective
- Extracts and stores article topics (if interests enabled)

**Returns**: Tuple of (Ray ObjectRef for commentary, article_id)

**Example Output**:
```
"Important insights in this article about renewable energy policies. We need more action on this front! #ClimateAction #RenewableEnergy"
```

#### Rule-Based Implementation

**Function**: `generate_rule_based_news_post(agent_id, cluster_id, article, news_service, article_id)`

**Behavior**:
- Saves article to database
- Creates empty or minimal content
- Article details referenced via article_id

**Returns**: Tuple of (ActionDTO, article_id)

#### Configuration

```json
{
  "simulation": {
    "actions_likelihood": {
      "news": 0.5
    }
  }
}
```

**Requirements**:
- Agent must be a page agent (is_page=1)
- Agent must have feed_url configured
- NewsFeedService must be running

**Related Documentation**:
- Page agents: [AGENT_TYPES.md](AGENT_TYPES.md#page-agents)
- RSS feed configuration: [CONFIG.md](../configuration/CONFIG.md#page-agents)

---

### 9. SEARCH (Search and Engage with Content)

Search for posts by topic and engage with results.

#### LLM Implementation

**Function**: `generate_llm_search_action_async(llm_handle, cluster_id, content, agent_attrs)`

**Behavior**:
- Agent searches for posts related to their interests
- LLM evaluates found post
- Decides engagement type: COMMENT, SHARE, LIKE, LOVE, LAUGH, ANGRY, SAD, IGNORE

**Returns**: Ray ObjectRef resolving to action type (str)

**Search Process**:
1. Select random topic from agent's interests
2. Query posts containing that topic
3. LLM decides how to engage
4. Execute corresponding action (comment, share, reaction)

#### Rule-Based Implementation

**Behavior**:
- Rule-based agents don't perform search actions
- Search is primarily for Explorer archetype (which typically uses LLM)

#### Configuration

```json
{
  "simulation": {
    "actions_likelihood": {
      "search": 5.0
    }
  }
}
```

**Archetype Availability**: Primarily Explorers, can be used by other archetypes if enabled

**Related Documentation**:
- Interest-based search: [INTERESTS.md](../features/INTERESTS.md)
- Explorer archetype: [AGENT_TYPES.md](AGENT_TYPES.md#explorer-archetype)

---

## Action Selection Mechanism

### Archetype-Based Selection

Agents select actions based on their archetype. See [AGENT_TYPES.md](AGENT_TYPES.md#agent-archetypes) for details.

**Validator** (Skeptical Consumers):
- Available: share, read, share_link
- Focus: Evaluating and sharing existing content

**Broadcaster** (Content Producers):
- Available: post, image, share, comment
- Focus: Creating and engaging with content

**Explorer** (Network Builders):
- Available: search, follow
- Focus: Discovering content and building network

### Likelihood-Based Selection

Within available actions, selection is weighted by likelihood values:

```python
# Example from simulation_config.json
"actions_likelihood": {
    "post": 3.0,      # 3x relative probability
    "comment": 5.0,   # 5x relative probability
    "read": 2.0,      # 2x relative probability
    "share": 1.0,     # 1x relative probability (baseline)
    "follow": 0.1     # 0.1x relative probability (rare)
}
```

**Selection Algorithm**:
1. Filter actions by archetype availability
2. Normalize probabilities (weights / sum of weights)
3. Random selection using weighted probability

**Disabling Actions**: Set likelihood to 0.0 to completely disable an action.

### Activity Level Impact

The `round_actions` profile variable determines how many actions an agent performs per time slot. See [AGENT_TEMPORAL_ACTIVITIES.md](AGENT_TEMPORAL_ACTIVITIES.md#round_actions).

---

## Implementation Details

### Scatter-Gather Pattern (LLM Actions)

LLM actions use Ray's async remote calls for parallel execution:

```python
# Scatter phase - launch multiple LLM calls in parallel
futures = []
for agent in active_agents:
    future = generate_llm_post_async(llm, agent.cluster, day, slot, agent_attrs)
    futures.append((agent.id, future))

# Gather phase - wait for all results at once
results = ray.get([f[1] for f in futures])

# Process results
for i, content in enumerate(results):
    agent_id = futures[i][0]
    action = ActionDTO(agent_id, cluster, "POST", content=content)
    submit_to_server(action)
```

**Benefits**:
- Parallel LLM calls (significant speedup)
- Non-blocking execution
- Efficient batch processing

### Text Annotation

All text content is automatically analyzed before submission:

```python
annotations = annotate_text(content)
# Returns:
# {
#     "hashtags": ["AI", "Technology"],
#     "mentions": ["alice", "bob"],
#     "sentiment": {"label": "positive", "score": 0.85},
#     "toxicity": {"label": "non-toxic", "score": 0.05}
# }
```

**Uses**:
- Hashtag extraction for topic analysis
- Mention detection for reply notifications
- Sentiment analysis for emotion tracking
- Toxicity detection for content moderation

**Related Documentation**: [ANNOTATION_IMPLEMENTATION.md](../features/ANNOTATION_IMPLEMENTATION.md)

### Opinion Updates (Comments Only)

When opinion dynamics is enabled, comment actions may include opinion updates:

```python
action.updated_opinions = {
    "topic_uuid": 0.65  # New opinion value [0, 1]
}
```

**Related Documentation**: [OPINION_DYNAMICS.md](../features/OPINION_DYNAMICS.md)

---

## Configuration

### Server-Side Configuration (server_config.json)

```json
{
  "posts": {
    "visibility_rounds": 36
  }
}
```

- `visibility_rounds`: How many time slots posts remain visible for recommendations

### Client-Side Configuration (simulation_config.json)

```json
{
  "simulation": {
    "actions_likelihood": {
      "post": 3.0,
      "image": 0.0,
      "news": 0.0,
      "comment": 5.0,
      "read": 2.0,
      "share": 1.0,
      "search": 5.0,
      "follow": 0.1
    },
    "agent_archetypes": {
      "enabled": true,
      "agent_downcast": false
    }
  },
  "agents": {
    "reading_from_follower_ratio": 0.6,
    "max_length_thread_reading": 5,
    "probability_of_daily_follow": 0.1,
    "probability_of_secondary_follow": 0.3
  }
}
```

### Agent-Specific Configuration (agent_population.json)

```json
{
  "id": 1,
  "username": "broadcaster_001",
  "archetype": "Broadcaster",
  "llm": true,
  "round_actions": 3,
  "recsys_type": "rchrono_followers",
  "frecsys_type": "common_neighbors"
}
```

- `archetype`: Determines available actions
- `llm`: Whether to use LLM or rule-based implementation
- `round_actions`: Number of actions per time slot
- `recsys_type`: Content recommendation strategy (for READ action)
- `frecsys_type`: Follow recommendation strategy (for FOLLOW action)

---

## Related Documentation

- **[AGENT_TYPES.md](AGENT_TYPES.md)**: Agent types, archetypes, and LLM vs rule-based behavior
- **[AGENT_TEMPORAL_ACTIVITIES.md](AGENT_TEMPORAL_ACTIVITIES.md)**: When agents act (hourly_activity, round_actions, activity_profiles)
- **[INTERESTS.md](../features/INTERESTS.md)**: Interest-based posting and learning
- **[OPINION_DYNAMICS.md](../features/OPINION_DYNAMICS.md)**: Opinion evolution through interactions
- **[RECOMMENDATION_SYSTEMS.md](../features/RECOMMENDATION_SYSTEMS.md)**: Content and follow recommendation algorithms
- **[EXTENDING.md](../development/EXTENDING.md)**: How to add new action types
- **[CONFIG.md](../configuration/CONFIG.md)**: Complete configuration reference
- **[ARCHITECTURE.md](../architecture/ARCHITECTURE.md)**: System architecture and action flow

---

**Last Updated**: January 2, 2026  
**Version**: 2.0
