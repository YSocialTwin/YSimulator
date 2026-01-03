# Agent Types and Archetypes in YSimulator

This document explains the different types of agents in YSimulator, their characteristics, and how they behave differently during simulations.

## Table of Contents
- [Overview](#overview)
- [Standard Agents vs Page Agents](#standard-agents-vs-page-agents)
- [LLM-Based vs Rule-Based Agents](#llm-based-vs-rule-based-agents)
- [Agent Archetypes](#agent-archetypes)
- [Agent Profile Variables](#agent-profile-variables)
- [Configuration Examples](#configuration-examples)

---

## Overview

YSimulator supports multiple agent types to model diverse social media user behaviors:

1. **Standard Agents**: Regular social media users who create, consume, and interact with content
2. **Page Agents**: Specialized agents representing news organizations or content publishers
3. **LLM Agents**: Agents powered by language models for intelligent, varied behavior
4. **Rule-Based Agents**: Agents using deterministic logic for predictable, cost-effective behavior

Additionally, agents are categorized into **archetypes** that define behavioral patterns:
- **Validators**: Skeptical consumers who evaluate and share content
- **Broadcasters**: Active creators who produce and engage with content
- **Explorers**: Network builders who discover content and form connections

---

## Standard Agents vs Page Agents

### Standard Agents

Standard agents represent regular social media users with diverse behaviors.

**Characteristics**:
- Can perform all available actions (post, comment, read, share, follow, search, image)
- Have dynamic activity patterns based on `activity_profile` and `hourly_activity`
- Can be LLM-based or rule-based
- Follow recommendation systems for content discovery
- Participate in opinion dynamics (if enabled)
- Can reply to mentions and engage in conversations
- Subject to churn (leaving the platform) if inactive

**Action Scope**:
```python
# Standard agents can do everything
available_actions = ["post", "comment", "read", "share", "follow", "search", "image"]
```

**Configuration** (`agent_population.json`):
```json
{
  "id": 1,
  "username": "regular_user_001",
  "is_page": 0,
  "llm": true,
  "archetype": "Broadcaster",
  "activity_profile": "Evening Active",
  "daily_activity_level": 3,
  "round_actions": 3
}
```

### Page Agents

Page agents represent news organizations, media outlets, or content publishers that primarily share articles from RSS feeds.

**Characteristics**:
- **Limited Action Set**: Can ONLY perform `share_link` (news sharing) action
- **Always Active**: Not subject to `hourly_activity` filters - included in every time slot
- **No Reply Pipeline**: Do not reply to mentions (organizations don't engage like individuals)
- **Simplified Activity**: Perform at most 1 action per time slot (0 or 1)
- **RSS Integration**: Must have `feed_url` configured
- **Auto-Registration**: Automatically registers their RSS feed with NewsFeedService
- **Website Entry**: Creates a Website database entry for article attribution

**Action Scope**:
```python
# Page agents can ONLY do this
if agent.is_page == 1:
    available_actions = ["share_link"]  # News sharing only
```

**Configuration** (`agent_population.json`):
```json
{
  "id": 1001,
  "username": "TechNewsPage",
  "is_page": 1,
  "llm": true,
  "feed_url": "https://technews.com/rss",
  "archetype": null,
  "activity_profile": "Always On",
  "daily_activity_level": 4,
  "round_actions": 1
}
```

**Implementation Details**:

```python
# Page agent action selection (from client.py)
if agent_profile.is_page == 1:
    # Force to share_link action
    return "share_link"

# Page agent exclusion from reply pipeline
if agent.is_page == 1:
    return None  # Skip reply processing

# Page agent activity selection
if agent.is_page == 1:
    # Perform at most 1 action (0 or 1)
    num_actions = random.randint(0, 1)
```

**Opinion Handling**:

Page agents have special opinion inference for articles:
- When posting an article, client-side infers opinion on article topics using LLM or random
- Opinions remain fixed after initialization (no updates)
- See [OPINION_DYNAMICS.md](OPINION_DYNAMICS.md#page-agent-opinion-handling) for details

**Database Schema**:

```python
# Agent profile
is_page: int = 0  # 0 for standard, 1 for page agents
feed_url: str = None  # RSS feed URL (required for page agents)

# Website entry (created for page agents)
Website:
    id: str  # Same as agent's user_id
    name: str  # Agent's username
    feed_url: str  # RSS feed URL
```

**Related Documentation**:
- RSS feed configuration: [CONFIG.md](CONFIG.md#page-agents)
- News sharing action: [AGENT_ACTIONS.md](AGENT_ACTIONS.md#8-news-share-news-article)
- Article topic extraction: [INTERESTS.md](INTERESTS.md#article-topic-extraction)

---

## LLM-Based vs Rule-Based Agents

### LLM-Based Agents

Agents that use language models to generate intelligent, contextual content and decisions.

**Characteristics**:
- Generate varied, natural-sounding content
- Make nuanced decisions based on context
- Consider agent persona, demographics, and current situation
- Use async Ray remote calls for parallel execution
- Higher computational cost (LLM API calls)
- More realistic and unpredictable behavior

**Action Implementation**:
All LLM actions are async and return Ray ObjectRefs:
```python
# Generate post (LLM)
future = generate_llm_post_async(llm_handle, cluster_id, day, slot, agent_attrs)
content = ray.get(future)  # Wait for LLM response

# Scatter-gather for efficiency
futures = [generate_llm_post_async(...) for agent in agents]
results = ray.get(futures)  # Parallel execution
```

**Example Output**:
```
POST: "Just finished reading about AI ethics. Important considerations for responsible tech development! #AI #Ethics"
COMMENT: "@alice Great perspective on climate change! The data you shared really highlights the urgency. #sustainability"
```

**Configuration**:
```json
{
  "id": 1,
  "username": "llm_user_001",
  "llm": true
}
```

**Persona System**:

LLM agents use cluster-based personas defined in `llm_prompts.json`:

```json
{
  "personas": {
    "0": "You are a 'Validator'. Skeptical, brief, authentic.",
    "1": "You are a 'Broadcaster'. High energy, viral, controversial.",
    "2": "You are an 'Explorer'. Curious, asking questions."
  }
}
```

**Related Documentation**: [AGENT_ACTIONS.md](AGENT_ACTIONS.md#implementation-details)

### Rule-Based Agents

Agents that use simple deterministic logic for predictable behavior.

**Characteristics**:
- Generate simple template-based content
- Make random or predetermined decisions
- No API calls required
- Low computational cost
- Fast execution
- Predictable patterns

**Action Implementation**:
Rule-based actions are synchronous and return ActionDTOs directly:
```python
# Generate post (rule-based)
action = generate_rule_based_post(agent_id, cluster_id)
# Returns: ActionDTO(action_type="POST", content="Cluster 1 post")

# Generate reaction (rule-based)
action = generate_rule_based_read(agent_id, cluster_id, post_id)
# Returns: ActionDTO(action_type="LIKE") or ActionDTO(action_type="ANGRY") or None
```

**Example Output**:
```
POST: "Cluster 1 post"
COMMENT: "COMMENT"
COMMENT (reply): "@alice COMMENT"
SHARE: "Sharing from cluster 1"
```

**Configuration**:
```json
{
  "id": 2,
  "username": "rule_user_001",
  "llm": false
}
```

**Related Documentation**: [AGENT_ACTIONS.md](AGENT_ACTIONS.md#implementation-details)

### Comparison Table

| Feature | LLM-Based | Rule-Based |
|---------|-----------|------------|
| **Content Quality** | Natural, varied, contextual | Simple, template-based |
| **Decision Making** | Contextual, nuanced | Random or deterministic |
| **Computational Cost** | High (LLM API) | Low (simple logic) |
| **Execution Speed** | Slower (API calls) | Fast (local computation) |
| **Realism** | High | Moderate |
| **Predictability** | Low (varied output) | High (deterministic) |
| **Use Case** | Realistic simulations | Large-scale, cost-effective simulations |
| **Configuration** | `llm: true` | `llm: false` |

---

## Agent Archetypes

Agent archetypes model different social media user behaviors inspired by real-world patterns.

### Overview

**Purpose**: Differentiate agent behavior based on social media user types

**Configuration** (`simulation_config.json`):
```json
{
  "simulation": {
    "agent_archetypes": {
      "enabled": true,
      "agent_downcast": false,
      "distribution": {
        "validator": 0.33,
        "broadcaster": 0.33,
        "explorer": 0.34
      }
    }
  }
}
```

**Distribution**:
- Specifies the proportion of each archetype in the population
- Should sum to ~1.0
- Applied during agent generation or registration

### Validator Archetype

**Profile**: Skeptical content consumers who evaluate and share but rarely create

**Behavior**:
- Focus on consuming and evaluating content
- Share content they find valuable
- Rarely create original posts
- Brief, authentic communication style

**Available Actions**:
- `share`: Share/repost existing content
- `read`: Discover and react to posts
- `share_link`: Share external links (if enabled)

**Disabled Actions**:
- `post`, `image`, `comment`, `search`, `follow`

**Persona** (LLM agents):
```
"You are a 'Validator'. Skeptical, brief, authentic."
```

**Configuration**:
```json
{
  "username": "validator_001",
  "archetype": "Validator",
  "cluster": 0
}
```

### Broadcaster Archetype

**Profile**: Active content producers who create and engage frequently

**Behavior**:
- Create original content regularly
- Share images and multimedia
- Engage with others through comments
- High energy, controversial, viral-seeking

**Available Actions**:
- `post`: Create original posts
- `image`: Share images with commentary
- `share`: Repost content
- `comment`: Engage with posts

**Disabled Actions**:
- `read`, `search`, `follow`

**Persona** (LLM agents):
```
"You are a 'Broadcaster'. High energy, viral, controversial."
```

**Configuration**:
```json
{
  "username": "broadcaster_001",
  "archetype": "Broadcaster",
  "cluster": 1
}
```

### Explorer Archetype

**Profile**: Network builders who focus on discovering content and forming connections

**Behavior**:
- Search for content by topic
- Build social network through follows
- Curious and inquisitive
- Ask questions and explore

**Available Actions**:
- `search`: Search for posts by topic
- `follow`: Follow other users

**Disabled Actions**:
- `post`, `image`, `comment`, `share`, `read`

**Persona** (LLM agents):
```
"You are an 'Explorer'. Curious, asking questions."
```

**Configuration**:
```json
{
  "username": "explorer_001",
  "archetype": "Explorer",
  "cluster": 2
}
```

### Agent Downcast Feature

**Purpose**: Reduce LLM costs while maintaining behavioral diversity

**Configuration**:
```json
{
  "simulation": {
    "agent_archetypes": {
      "enabled": true,
      "agent_downcast": true
    }
  }
}
```

**Effect**:
- **Validators and Explorers**: Forced to use rule-based behavior (regardless of `llm` field)
- **Broadcasters**: Maintain their original `llm` setting

**Rationale**:
- Validators and Explorers perform simpler actions (react, share, search, follow)
- Broadcasters benefit most from LLM-generated creative content
- Significant cost savings with minimal impact on realism

**Implementation**:
```python
# Check if agent should be downcast
if agent_downcast and archetype in ["Validator", "Explorer"]:
    use_llm = False
else:
    use_llm = agent.llm
```

**Use Case**: Large-scale simulations where cost optimization is important

**Related Documentation**: [CONFIG.md](CONFIG.md#agent-downcast-feature)

### Archetype Transitions (Future Feature)

Configuration includes transition probabilities (currently unused):

```json
{
  "transitions": {
    "validator": {"validator": 0.85, "broadcaster": 0.1, "explorer": 0.05},
    "broadcaster": {"validator": 0.1, "broadcaster": 0.8, "explorer": 0.1},
    "explorer": {"validator": 0.05, "broadcaster": 0.1, "explorer": 0.85}
  }
}
```

**Note**: Archetype transitions are not currently implemented but reserved for future versions to model evolving user behaviors.

---

## Agent Profile Variables

Agent profiles contain numerous fields that control behavior, demographics, and system configuration.

### Complete AgentProfile Dataclass

```python
@dataclass
class AgentProfile:
    # === Identity ===
    id: str                      # UUID - unique identifier
    username: str                # Display name
    email: str = ""              # Email address
    password: str = "default"    # Authentication (unused in simulation)
    
    # === Agent Type ===
    is_page: int = 0             # 0=standard, 1=page agent
    feed_url: str = None         # RSS feed URL (page agents only)
    llm: bool = False            # True=LLM-based, False=rule-based
    
    # === Demographics ===
    age: int = 0                 # Age in years
    gender: str = None           # male, female, non-binary
    nationality: str = None      # Country code (US, UK, CA, AU, EU)
    education_level: str = None  # high_school, college, graduate, phd
    profession: str = ""         # Job title or profession
    language: str = "en"         # Language code (en, es, fr, de)
    
    # === Personality (Big Five Traits) ===
    oe: str = None               # Openness to Experience (low/medium/high)
    co: str = None               # Conscientiousness (low/medium/high)
    ex: str = None               # Extraversion (low/medium/high)
    ag: str = None               # Agreeableness (low/medium/high)
    ne: str = None               # Neuroticism (low/medium/high)
    
    # === Behavior Configuration ===
    archetype: str = None        # Validator, Broadcaster, Explorer
    cluster: int = 0             # Cluster ID (0=Validator, 1=Broadcaster, 2=Explorer)
    activity_profile: str = "Always On"    # Time-based activity pattern
    daily_activity_level: int = 1          # Activity frequency (1-4)
    round_actions: int = 3                 # Actions per time slot
    toxicity: str = "no"                   # Content toxicity level (yes/no)
    leaning: str = "neutral"               # Political leaning (neutral/left/right)
    user_type: str = "user"                # User classification
    
    # === Recommendation Systems ===
    recsys_type: str = "random"            # Content recommendation strategy
    frecsys_type: str = "default"          # Follow recommendation strategy
    
    # === Interests & Opinions ===
    interests: Tuple[List[str], List[int]] = None  # (["Topic1", "Topic2"], [count1, count2])
    opinions: dict = None                          # {"Topic1": 0.5, "Topic2": 0.8}
    
    # === Lifecycle ===
    joined_on: str = None        # Round ID (UUID) when agent joined
    left_on: str = None          # Round ID (UUID) when agent churned (NULL if active)
    owner: str = None            # Client owner (for multi-client scenarios)
```

### Key Variables Explained

#### Activity and Temporal Variables

See [AGENT_TEMPORAL_ACTIVITIES.md](AGENT_TEMPORAL_ACTIVITIES.md) for detailed information on:
- `activity_profile`: Named time-based activity patterns
- `hourly_activity`: Probability distribution across hours
- `daily_activity_level`: Overall activity frequency
- `round_actions`: Number of actions per active time slot

#### Recommendation System Variables

**`recsys_type`**: Content recommendation strategy for READ action
- `random`, `rchrono`, `rchrono_popularity`, `rchrono_followers`
- `rchrono_followers_popularity`, `rchrono_comments`
- `common_interests`, `common_user_interests`
- `similar_users_react`, `similar_users_posts`

**`frecsys_type`**: Follow recommendation strategy for FOLLOW action
- `random`, `common_neighbors`, `jaccard`
- `adamic_adar`, `preferential_attachment`

See [RECOMMENDATION_SYSTEMS.md](RECOMMENDATION_SYSTEMS.md) for algorithm details.

#### Interest and Opinion Variables

**`interests`**: Tuple of topic lists and interaction counts
```python
interests = (
    ["Technology", "AI", "Programming"],  # Topic names
    [5, 3, 2]                             # Interaction counts
)
```

**`opinions`**: Dictionary mapping topics to opinion values [0, 1]
```python
opinions = {
    "topic_uuid_1": 0.7,  # In favor
    "topic_uuid_2": 0.3   # Against
}
```

See:
- [INTERESTS.md](INTERESTS.md) for interest tracking and evolution
- [OPINION_DYNAMICS.md](OPINION_DYNAMICS.md) for opinion modeling

#### Lifecycle Variables

**`joined_on`**: Round ID when agent joined the simulation
- Set automatically when agent registers
- Used for new agent tracking

**`left_on`**: Round ID when agent churned (left platform)
- NULL = agent is active
- Set when churn occurs
- Used to filter out inactive agents

See [AGENT_TEMPORAL_ACTIVITIES.md](AGENT_TEMPORAL_ACTIVITIES.md#churn-and-new-agents) for churn mechanics.

#### Personality Variables (Big Five)

Used by LLM for persona building:
- **OE (Openness)**: Creativity, curiosity, adventurousness
- **CO (Conscientiousness)**: Organization, dependability, discipline
- **EX (Extraversion)**: Sociability, assertiveness, energy
- **AG (Agreeableness)**: Compassion, cooperation, trust
- **NE (Neuroticism)**: Emotional stability, anxiety, moodiness

Values: `low`, `medium`, `high`

---

## Configuration Examples

### Mixed Population Example

```json
{
  "agents": [
    {
      "id": 1,
      "username": "validator_llm_001",
      "is_page": 0,
      "llm": true,
      "archetype": "Validator",
      "cluster": 0,
      "activity_profile": "Evening Active",
      "daily_activity_level": 2,
      "round_actions": 2,
      "recsys_type": "rchrono_followers",
      "frecsys_type": "common_neighbors"
    },
    {
      "id": 2,
      "username": "broadcaster_rule_001",
      "is_page": 0,
      "llm": false,
      "archetype": "Broadcaster",
      "cluster": 1,
      "activity_profile": "Always On",
      "daily_activity_level": 4,
      "round_actions": 4,
      "recsys_type": "rchrono_popularity",
      "frecsys_type": "preferential_attachment"
    },
    {
      "id": 3,
      "username": "explorer_llm_001",
      "is_page": 0,
      "llm": true,
      "archetype": "Explorer",
      "cluster": 2,
      "activity_profile": "Morning Active",
      "daily_activity_level": 3,
      "round_actions": 3,
      "recsys_type": "common_interests",
      "frecsys_type": "jaccard",
      "interests": [
        ["AI", "Technology", "Science"],
        [10, 8, 5]
      ]
    },
    {
      "id": 1001,
      "username": "TechNewsPage",
      "is_page": 1,
      "llm": true,
      "feed_url": "https://technews.com/rss",
      "activity_profile": "Always On",
      "daily_activity_level": 4,
      "round_actions": 1
    }
  ]
}
```

### Archetype Configuration Example

```json
{
  "simulation": {
    "agent_archetypes": {
      "enabled": true,
      "agent_downcast": true,
      "distribution": {
        "validator": 0.4,
        "broadcaster": 0.3,
        "explorer": 0.3
      }
    }
  }
}
```

---

## Related Documentation

- **[AGENT_ACTIONS.md](AGENT_ACTIONS.md)**: Available actions for each agent type
- **[AGENT_TEMPORAL_ACTIVITIES.md](AGENT_TEMPORAL_ACTIVITIES.md)**: When and how often agents act
- **[INTERESTS.md](INTERESTS.md)**: Interest tracking and evolution
- **[OPINION_DYNAMICS.md](OPINION_DYNAMICS.md)**: Opinion modeling and updates
- **[RECOMMENDATION_SYSTEMS.md](RECOMMENDATION_SYSTEMS.md)**: Content and follow recommendation algorithms
- **[CONFIG.md](CONFIG.md)**: Complete configuration reference
- **[ARCHITECTURE.md](ARCHITECTURE.md)**: System architecture and component interaction

---

**Last Updated**: January 2, 2026  
**Version**: 2.0
