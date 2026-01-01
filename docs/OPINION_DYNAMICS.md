# Opinion Dynamics Models

## Overview

YSimulator implements a comprehensive **opinion dynamics system** with support for **two opinion update models**. This system tracks and evolves agent opinions on various topics throughout the simulation, enabling realistic opinion formation, polarization effects, and opinion-based interactions.

The opinion dynamics module allows agents to:
- Maintain numeric opinions on topics (ranging from 0 to 1)
- Update opinions through social interactions (comments, shares)
- Form new opinions when encountering new topics
- Express opinions in content generation and reactions

**Related Documentation:**
- **[Configuration Guide (CONFIG.md)](CONFIG.md)** - Opinion dynamics configuration in `simulation_config.json`
- **[Redis Integration (RECSYS_REDIS_SUPPORT.md)](RECSYS_REDIS_SUPPORT.md)** - Redis support status for opinion dynamics
- **[Architecture Overview (ARCHITECTURE.md)](ARCHITECTURE.md)** - System architecture and component interactions
- **[Example Configurations](../example/)** - Example directories with different opinion dynamics setups

## Supported Models

YSimulator supports two opinion dynamics models:

1. **Bounded Confidence Model** (`bounded_confidence`)
   - Classic opinion dynamics based on confidence bounds
   - Mathematical model with convergence/polarization
   - Works for all agent types (LLM and rule-based)

2. **LLM Evaluation Model** (`llm_evaluation`)
   - LLM-based opinion reasoning
   - Natural language evaluation of agreement/disagreement
   - Works only for LLM-based agents
   - Can consider opinions of neighbors in evaluation

---

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [Configuration](#configuration)
3. [Bounded Confidence Model](#bounded-confidence-model)
4. [LLM Evaluation Model](#llm-evaluation-model)
5. [Opinion Storage](#opinion-storage)
6. [Opinion Updates](#opinion-updates)
7. [Page Agent Opinion Handling](#page-agent-opinion-handling)
8. [Opinion-Based Interactions](#opinion-based-interactions)
9. [Implementation Architecture](#implementation-architecture)
10. [API Reference](#api-reference)
11. [Examples](#examples)

---

## Core Concepts

### Opinion Values

Opinions are represented as **continuous numeric values** in the range **[0, 1]**:
- `0.0` = Strongly against
- `0.5` = Neutral stance
- `1.0` = Strongly in favor

### Opinion Groups

For better interpretability, numeric opinions are mapped to **discrete opinion groups** defined in the configuration:

```json
"opinion_groups": {
  "Strongly against": [0.0, 0.2],
  "Against": [0.2, 0.4],
  "Neutral": [0.4, 0.6],
  "In favor": [0.6, 0.8],
  "Strongly in favor": [0.8, 1.0]
}
```

These groups are used when:
- LLM agents generate content (prompts include discrete labels)
- LLM agents infer opinions from article content
- Logging and debugging opinion states

### Agent Types and Opinions

**Regular Agents:**
- Have initial opinions defined in `agent_population.json`
- Opinions evolve through interactions via bounded confidence model
- Always use their most recent opinion from database

**Page Agents:**
- Post articles about various topics
- **Rule-based pages**: Generate random opinions [0, 1] for new topics
- **LLM-based pages**: Infer opinions from article content using LLM
- Page agent opinions remain **fixed** after initialization (no updates)

---

## Configuration

### Enabling Opinion Dynamics

Opinion dynamics is controlled via the `opinion_dynamics` section in `simulation_config.json`:

```json
{
  "opinion_dynamics": {
    "enabled": true,
    "model_name": "bounded_confidence",
    "parameters": {
      "epsilon": 0.25,
      "mu": 0.5,
      "theta": 0.0,
      "cold_start": "neutral"
    },
    "opinion_groups": {
      "Strongly against": [0.0, 0.2],
      "Against": [0.2, 0.4],
      "Neutral": [0.4, 0.6],
      "In favor": [0.6, 0.8],
      "Strongly in favor": [0.8, 1.0]
    }
  }
}
```

### Disabling Opinion Dynamics

To disable opinion dynamics, set `enabled` to `false`:

```json
{
  "opinion_dynamics": {
    "enabled": false
  }
}
```

When disabled:
- No opinion updates occur during interactions
- Agents can still have initial opinions defined in `agent_population.json`
- Opinion-based content generation and reactions still work with initial opinions
- No opinion records are stored in the database beyond initial values
- The simulation runs normally without any opinion evolution

You can also completely omit the `opinion_dynamics` section from the configuration, which is equivalent to setting `enabled: false`.

### Configuration Parameters

| Parameter | Type | Description | Default | Models |
|-----------|------|-------------|---------|--------|
| `enabled` | boolean | Master switch for opinion dynamics | `true` | Both |
| `model_name` | string | Opinion update model: `"bounded_confidence"` or `"llm_evaluation"` | `"bounded_confidence"` | Both |
| `epsilon` | float | Confidence bound threshold | `0.25` | bounded_confidence |
| `mu` | float | Convergence rate when within bound (0-1) | `0.5` | bounded_confidence |
| `theta` | float | Polarization rate when outside bound | `0.0` | bounded_confidence |
| `evaluation_scope` | string | `"interlocutor_only"` or `"neighbors"` | `"interlocutor_only"` | llm_evaluation |
| `cold_start` | string | Strategy for agents with no prior opinion: `"neutral"` or `"inherited"` | `"neutral"` | Both |

### Initial Agent Opinions

Agent opinions are specified in `agent_population.json`:

```json
{
  "username": "agent_042",
  "interests": [["Technology", "AI", "Research"], [8, 7, 9]],
  "opinions": {
    "Technology": 0.7364,
    "AI": 0.6766,
    "Research": 0.8923
  }
}
```

---

## Bounded Confidence Model

### Model Description

The bounded confidence model is a classic opinion dynamics model where:
- Agents only update opinions when interacting with similar agents
- The **epsilon (ε)** parameter defines the "confidence bound"
- Opinions converge to clusters based on interaction patterns

### Mathematical Formulation

Given two agents with opinions **x** (current agent) and **y** (other agent):

#### Case 1: Opinion Difference Within Confidence Bound

If `|y - x| ≤ ε`:
```
x_new = x + μ × (y - x)
```

The agent moves toward the other agent's opinion at rate **μ**, converging their positions.

#### Case 2: Opinion Difference Exceeds Confidence Bound

If `|y - x| > ε` and `θ ≠ 0`:
```
x_new = x + θ    if x > y (polarize further right)
x_new = x - θ    if x < y (polarize further left)
```

The agent polarizes away from the other agent at rate **θ**.

#### Case 3: Cold Start

If agent has no prior opinion (`x = None`):

**Neutral strategy** (`cold_start = "neutral"`):
```
x = 0.5
```

**Inherited strategy** (`cold_start = "inherited"`):
```
x = y
```

### Parameter Effects

**Epsilon (ε)** - Confidence Bound:
- **Small ε (0.1-0.3)**: Agents only influenced by very similar opinions → **opinion clustering**
- **Large ε (0.5-1.0)**: Agents influenced by diverse opinions → **consensus formation**

**Mu (μ)** - Convergence Rate:
- **Small μ (0.1-0.3)**: Slow convergence toward similar opinions
- **Large μ (0.7-0.9)**: Rapid convergence toward similar opinions
- Controls the strength of opinion update when within confidence bound

**Theta (θ)** - Polarization Rate:
- **θ = 0**: No polarization (default)
- **θ > 0**: Opinions polarize away from dissimilar agents by θ units per interaction
- Only active when opinion difference exceeds epsilon

**Cold Start Strategy**:
- **"neutral"**: New agents start with neutral opinion (0.5)
- **"inherited"**: New agents adopt the opinion of the agent they interact with

### Implementation

The bounded confidence function is located in:
```
YSimulator/YClient/opinion_dynamics/confidence_bound.py
```

```python
def bounded_confidence(x: float, y: float, epsilon: float = 0.25,
                      mu: float = 0.5, theta: float = 0.0,
                      cold_start: str = "neutral") -> float:
    """
    Calculate opinion update using bounded confidence model.
    
    Parameters:
    - x: Current agent's opinion (can be None for cold start)
    - y: Other agent's opinion (must not be None)
    - epsilon: Confidence bound threshold
    - mu: Update rate
    - theta: Polarization parameter
    - cold_start: Strategy when x is None ("neutral" or "inherited")
    
    Returns:
    - Updated opinion value in [0, 1]
    """
```

---

## LLM Evaluation Model

### Model Description

The LLM evaluation model uses **natural language reasoning** to evaluate opinion updates. Instead of mathematical formulas, this model:
- Uses LLM to assess whether an agent agrees, disagrees, or remains neutral about a post
- Shifts opinions between discrete opinion classes based on the assessment
- Can optionally consider the opinions of the agent's social network neighbors

This model is **only available for LLM-based agents** as it requires language understanding capabilities.

### Configuration

The LLM evaluation model is specified in `simulation_config.json`:

```json
{
  "opinion_dynamics": {
    "enabled": true,
    "model_name": "llm_evaluation",
    "parameters": {
      "evaluation_scope": "interlocutor_only",
      "cold_start": "neutral"
    },
    "opinion_groups": {
      "Strongly against": [0.0, 0.2],
      "Against": [0.2, 0.4],
      "Neutral": [0.4, 0.6],
      "In favor": [0.6, 0.8],
      "Strongly in favor": [0.8, 1.0]
    }
  }
}
```

### Parameters

| Parameter | Type | Values | Description | Default |
|-----------|------|--------|-------------|---------|
| `evaluation_scope` | string | `"interlocutor_only"` or `"neighbors"` | Scope of opinion evaluation | `"interlocutor_only"` |
| `cold_start` | string | `"neutral"` or `"inherited"` | Strategy for agents with no prior opinion | `"neutral"` |

**evaluation_scope options:**
- `"interlocutor_only"`: LLM only considers the post author's opinion
- `"neighbors"`: LLM also considers the opinions of agents the reader follows

### How It Works

#### Step 1: Opinion Assessment

The LLM is prompted to evaluate whether the agent agrees, disagrees, or remains neutral about the post:

```
Read the following text on the topic 'CLIMATE CHANGE': 
'Renewable energy is the future we need to embrace for our planet...'

The author has opinion 'Strongly in favor' on the topic.
Your initial opinion is 'Neutral'

[If evaluation_scope = "neighbors"]
The following are the opinions of your friends:
Opinion: 'In favor' (5)
Opinion: 'Strongly in favor' (3)
Opinion: 'Neutral' (2)

What do you think about the expressed opinion? 
Answer with a single word among the options: AGREE|DISAGREE|NEUTRAL.
```

#### Step 2: Opinion Shift

Based on the LLM's response, the opinion is shifted:

- **AGREE**: Move one step towards the author's opinion class
  - Example: "Neutral" → "In favor" (when author is "Strongly in favor")
- **DISAGREE**: Move one step away from the author's opinion class
  - Example: "Neutral" → "Against" (when author is "Strongly in favor")
- **NEUTRAL**: No change to opinion

#### Step 3: Boundary Clamping

Opinion shifts are clamped at the boundaries:
- Cannot move beyond "Strongly against" (lower bound)
- Cannot move beyond "Strongly in favor" (upper bound)

### Opinion Class Shift Logic

The `shift_class` function handles opinion shifts:

```python
def shift_class(current_class, author_class, direction, opinion_groups):
    """
    Shift opinion from current_class towards or away from author_class.
    
    Args:
        current_class: Agent's current opinion label (e.g., "Neutral")
        author_class: Author's opinion label (e.g., "In favor")
        direction: Direction.AGREE or Direction.DISAGREE
        opinion_groups: Opinion class definitions
    
    Returns:
        (new_label, new_value) where new_value is the midpoint of new class
    """
```

**Examples:**

1. **Agreement Shift:**
   - Current: "Neutral" [0.4, 0.6] → mid = 0.5
   - Author: "In favor" [0.6, 0.8]
   - Direction: AGREE
   - Result: "In favor" → mid = 0.7

2. **Disagreement Shift:**
   - Current: "Neutral" [0.4, 0.6] → mid = 0.5
   - Author: "In favor" [0.6, 0.8]
   - Direction: DISAGREE
   - Result: "Against" [0.2, 0.4] → mid = 0.3

3. **Same Class:**
   - Current: "Neutral"
   - Author: "Neutral"
   - Direction: AGREE
   - Result: "Neutral" (no change)

4. **Boundary Clamping:**
   - Current: "Strongly against"
   - Author: "In favor"
   - Direction: DISAGREE
   - Result: "Strongly against" (already at lower bound)

### Cold Start Behavior

When an agent encounters a topic for the first time:

**Neutral Strategy (`cold_start = "neutral"`):**
```python
x = 0.5  # Start at midpoint
```

**Inherited Strategy (`cold_start = "inherited"`):**
```python
x = y  # Adopt author's opinion
```

### Implementation

The LLM evaluation function is located in:
```
YSimulator/YClient/opinion_dynamics/llm_evaluation.py
```

```python
def llm_evaluation(
    x: float,             # Agent's current opinion (can be None)
    y: float,             # Author's opinion (must not be None)
    text: str,            # Post content
    topic: str,           # Topic name
    evaluation_scope: str,  # "interlocutor_only" or "neighbors"
    cold_start: str,      # "neutral" or "inherited"
    group_classes: dict,  # Opinion group definitions
    peers_opinions: list, # List of (label, count) tuples
    llm_service          # Ray actor reference to LLMService
) -> float:
    """
    LLM-based opinion evaluation.
    
    Returns: Updated opinion value in [0, 1]
    """
```

The LLM interaction is handled in:
```
YSimulator/YClient/LLM_interactions/llm_service.py
```

```python
def evaluate_opinion(
    self, 
    agent_opinion: str,     # Agent's opinion label
    author_opinion: str,    # Author's opinion label
    post_text: str,         # Post content
    topic: str,             # Topic name
    peers_opinions: list    # Optional neighbors' opinions
) -> str:
    """
    Use LLM to evaluate agreement/disagreement.
    
    Returns: "AGREE", "DISAGREE", or "NEUTRAL"
    """
```

### Advantages

- **Natural Language Understanding**: LLM can understand nuanced expressions of opinion
- **Context-Aware**: Can consider post content semantics, not just numeric values
- **Social Context**: Can incorporate neighbors' opinions in evaluation
- **Realistic**: Models how humans actually evaluate opinions

### Limitations

- **LLM Agents Only**: Requires language model capabilities
- **Computational Cost**: LLM inference is slower than mathematical models
- **Determinism**: LLM responses may vary slightly between runs
- **Discrete Shifts**: Only moves one opinion class at a time

---

## Opinion Storage

### Database Model

Opinions are stored in the `agent_opinion` table:

```python
# SQLAlchemy model (simplified for documentation)
class Agent_Opinion:
    id: String(36)           # Primary key, UUID
    agent_id: String(36)     # Agent UUID (NOT NULL)
    tid: String(36)          # Round ID (NOT NULL)
    topic_id: String(36)     # Topic reference (NOT NULL, FK to interests.iid)
    id_interacted_with: String(36)  # Other agent ID (optional)
    id_post: String(36)      # Post reference (optional, FK to post.id)
    opinion: Float           # Opinion value in [0,1] (NOT NULL)
```

### Opinion Records

Each opinion record captures:
- **Agent ID**: Which agent holds the opinion
- **Round ID**: When the opinion was recorded
- **Topic ID**: Which topic the opinion is about
- **Interacted With**: Agent ID of interaction partner (optional)
- **Post ID**: Post that triggered the opinion update (optional)
- **Opinion Value**: Numeric opinion in [0, 1]

### Opinion History

The system maintains a **complete history** of opinion evolution:
- Initial opinions stored at agent registration
- New opinion records created after each interaction
- Latest opinion retrieved via `get_latest_agent_opinion(agent_id, topic_id)`

---

## Opinion Updates

### When Opinions Update

Opinions are updated when agents perform these actions:

1. **Comment on a post**
   - Agent reads post topics
   - Retrieves author's opinions on those topics
   - Calculates new opinion via bounded confidence
   - Stores updated opinion in database

2. **Share a post**
   - Same process as commenting
   - Opinion updated based on original author's stance

### Opinion Update Flow

```
1. Agent performs COMMENT or SHARE action
2. Client retrieves post topics
3. Client fetches author's latest opinions (y)
4. Client fetches agent's latest opinions (x)
5. Client calculates new opinions using bounded_confidence()
6. Client attaches updated opinions to ActionDTO
7. Server stores new opinions in agent_opinion table
```

### Client-Side Evaluation

**All opinion calculations happen on the client side:**

```python
def _calculate_opinion_updates(self, agent_id, parent_post_id, parent_author_id):
    """Calculate opinion updates for comment/share actions."""
    if not self._is_opinion_dynamics_enabled():
        return {}
    
    # Get post topics
    post_topics = ray.get(
        self.server.get_post_topics.remote(parent_post_id)
    )
    
    updated_opinions = {}
    
    for topic_id in post_topics:
        # Get author's opinion (y)
        author_opinion = ray.get(
            self.server.get_latest_agent_opinion.remote(
                parent_author_id, topic_id
            )
        )
        
        if author_opinion is None:
            # Data inconsistency - skip
            continue
        
        # Get agent's opinion (x)
        agent_opinion = ray.get(
            self.server.get_latest_agent_opinion.remote(
                agent_id, topic_id
            )
        )
        
        # Calculate new opinion
        params = self.simulation_config["opinion_dynamics"]["parameters"]
        new_opinion = bounded_confidence(
            agent_opinion,
            author_opinion,
            epsilon=params.get("epsilon", 0.25),
            mu=params.get("mu", 0.5),
            theta=params.get("theta", 0.0),
            cold_start=params.get("cold_start", "neutral")
        )
        
        updated_opinions[topic_id] = new_opinion
    
    return updated_opinions
```

### Server-Side Storage

The server receives pre-calculated opinions and stores them:

```python
# In submit_actions():
for action in actions:
    if action.updated_opinions:
        for topic_id, opinion_value in action.updated_opinions.items():
            self.db.add_agent_opinion(
                action.agent_id,
                self.current_round_id,
                topic_id,
                opinion_value,
                id_interacted_with=action.target_id,
                id_post=action.post_id
            )
```

---

## Page Agent Opinion Handling

Page agents post articles about various topics and need opinions on those topics.

### Rule-Based Page Agents

When a rule-based page agent posts an article on a new topic:

```python
def _infer_page_agent_opinion(self, agent_id, article_content, topic_name):
    """Infer opinion for page agent on article topic."""
    agent_profile = next(
        (a for a in self.agent_profiles if a.id == agent_id), None
    )
    
    # Rule-based page: random opinion
    if not agent_profile.llm:
        return random.random()
    
    # LLM page: infer from article content
    # ...
```

**Characteristics:**
- Generate `random.random()` value in [0, 1]
- Opinion stored in database
- Opinion remains fixed for that topic

### LLM-Based Page Agents

LLM-based pages infer opinions from article content:

```python
def infer_article_opinion(self, article_text, topic, opinion_groups):
    """
    Use LLM to infer article's stance on a topic.
    
    Process:
    1. Format opinion_groups as prompt options
    2. Ask LLM to select category
    3. Map selected category to numeric value (midpoint of range)
    4. Return opinion value
    """
```

**Example:**

Article: "This new AI technology will revolutionize healthcare..."
Topic: "AI"

LLM Prompt:
```
Analyze this article and determine its stance on the topic 'AI'.

Article excerpt:
This new AI technology will revolutionize healthcare...

What is the article's stance? Choose ONLY ONE from these options:
- Strongly against
- Against
- Neutral
- In favor
- Strongly in favor

Your choice (ONE WORD ONLY):
```

LLM Response: "In favor"

Mapping: "In favor" → [0.6, 0.8] → midpoint = 0.7

**Characteristics:**
- Context-aware opinions based on article content
- Uses discrete opinion_groups for clarity
- Maps category to numeric value
- Opinion stored in database
- Opinion remains fixed for that topic

### Opinion Inference Integration

Opinion inference happens **before POST action submission**:

```python
def _handle_share_link_action(self, agent_profile, link):
    """Handle page agent posting article."""
    # ... extract/store topics ...
    
    # Infer and store opinions for page agent
    if self._is_opinion_dynamics_enabled():
        for topic_id in topic_ids:
            topic_name = get_topic_name(topic_id)
            
            # Check if opinion exists
            existing_opinion = ray.get(
                self.server.get_latest_agent_opinion.remote(
                    agent_profile.id, topic_id
                )
            )
            
            if existing_opinion is None:
                # Infer opinion
                opinion_value = self._infer_page_agent_opinion(
                    agent_profile.id,
                    article_content,
                    topic_name
                )
                
                # Store opinion
                ray.get(
                    self.server.add_agent_opinion.remote(
                        agent_profile.id,
                        topic_id,
                        opinion_value,
                        None,
                        None
                    )
                )
```

---

## Opinion-Based Interactions

### LLM Post Generation

When LLM agents generate posts, their opinions are included in prompts:

```python
def _extract_agent_attrs(self, agent_profile, topic=None):
    """Extract agent attributes including opinions."""
    attrs = {...}
    
    if topic and self._is_opinion_dynamics_enabled():
        # Get agent's opinion on topic
        opinion_value = get_latest_opinion(agent_profile.id, topic)
        
        # Map to discrete label
        opinion_label = self._map_opinion_to_group(opinion_value)
        
        attrs["topic_opinion"] = opinion_label
        attrs["topic_opinion_value"] = opinion_value
    
    return attrs
```

**Prompt Example:**
```
You are agent_042, a 28-year-old from New York interested in Technology.
Your opinion on this topic is: In favor
Express this viewpoint in your post.

Generate a post about: Latest AI developments
```

### LLM Comments and Shares

When commenting/sharing, agents express their opinions:

```python
# Get agent's opinions on post topics
opinions = self._get_opinions_for_post(agent_id, post_id)

# Format for prompt
opinion_text = "\n".join([
    f"{topic}: {self._map_opinion_to_group(value)}"
    for topic, value in opinions.items()
])

prompt += f"\nYour opinions on the discussed topics:\n{opinion_text}"
prompt += "\nExpress your viewpoint accordingly."
```

### Rule-Based Reactions

Rule-based agents' reactions are influenced by opinions:

```python
def _choose_reaction_based_on_opinion(self, opinion_value):
    """Choose reaction based on opinion value."""
    if opinion_value > 0.6:
        # Positive opinion
        return random.choice(["LIKE", "LOVE", "LIKE"])
    elif opinion_value < 0.4:
        # Negative opinion
        return random.choice(["ANGRY", "SAD", "IGNORE"])
    else:
        # Neutral opinion
        return random.choice(["LIKE", "IGNORE", "ANGRY"])
```

### LLM Reactions

LLM agents receive opinion context for reactions:

```python
opinions = self._get_opinions_for_post(agent_id, post_id)
opinion_text = format_opinions(opinions)

prompt = f"""
Post content: {post_content}
Your opinions: {opinion_text}

React accordingly. Choose: LIKE, LOVE, ANGRY, SAD, or IGNORE
"""
```

---

## Implementation Architecture

### Client-Side Components

**Location:** `YSimulator/YClient/client.py`

**Key Methods:**

```python
def _is_opinion_dynamics_enabled(self) -> bool:
    """Check if opinion dynamics is enabled in config."""

def _calculate_opinion_updates(self, agent_id, post_id, author_id) -> Dict:
    """Calculate opinion updates for interaction."""

def _get_opinions_for_post(self, agent_id, post_id) -> Dict:
    """Get agent's opinions on all topics in post."""

def _map_opinion_to_group(self, opinion_value: float) -> str:
    """Map numeric opinion to discrete label."""

def _infer_page_agent_opinion(self, agent_id, article, topic) -> float:
    """Infer page agent opinion (random or LLM)."""
```

### Server-Side Components

**Location:** `YSimulator/YServer/server.py`

**Key Methods:**

```python
def add_agent_opinion(self, agent_id, topic_id, opinion, ...):
    """Store agent opinion in database."""

def get_latest_agent_opinion(self, agent_id, topic_id) -> Optional[float]:
    """Retrieve agent's most recent opinion on topic."""

def get_post_topics(self, post_id) -> List[str]:
    """Get all topic IDs associated with a post."""

def get_topic_name_from_id(self, topic_id) -> Optional[str]:
    """Look up topic name from topic ID."""
```

### Database Layer

**Location:** `YSimulator/YServer/classes/db_middleware.py`

**Key Methods:**

```python
def add_agent_opinion(self, agent_id, round_id, topic_id, 
                      opinion, id_interacted_with, id_post):
    """Insert opinion record into agent_opinion table."""

def get_latest_agent_opinion(self, agent_id, topic_id):
    """Query most recent opinion record for agent-topic pair."""

def get_topic_name_from_id(self, topic_id):
    """Query interests table for topic name."""
```

### LLM Service

**Location:** `YSimulator/YClient/LLM_interactions/llm_service.py`

**Key Methods:**

```python
def infer_article_opinion(self, article_text, topic, opinion_groups):
    """
    Use LLM to infer opinion from article.
    
    Returns: float in [0, 1]
    """

def generate_post(self, agent_attrs, topic):
    """
    Generate post with opinion context.
    
    agent_attrs includes:
    - topic_opinion: discrete label
    - topic_opinion_value: numeric value
    """
```

### Opinion Dynamics Module

**Location:** `YSimulator/YClient/opinion_dynamics/`

**Files:**
- `confidence_bound.py`: Bounded confidence model implementation
- `llm_evaluation.py`: LLM-based opinion evaluation
- `utils.py`: Helper functions

---

## API Reference

### Client API

#### `_is_opinion_dynamics_enabled() -> bool`

Check if opinion dynamics is enabled in simulation config.

**Returns:** `True` if enabled, `False` otherwise

#### `_calculate_opinion_updates(agent_id, post_id, author_id) -> Dict[str, float]`

Calculate opinion updates for a comment/share action.

**Parameters:**
- `agent_id`: ID of agent performing action
- `post_id`: ID of post being interacted with
- `author_id`: ID of post author

**Returns:** Dictionary mapping topic_id → new_opinion_value

#### `_get_opinions_for_post(agent_id, post_id) -> Dict[str, float]`

Get agent's opinions on all topics in a post.

**Parameters:**
- `agent_id`: Agent ID
- `post_id`: Post ID

**Returns:** Dictionary mapping topic_id → opinion_value

#### `_map_opinion_to_group(opinion_value: float) -> str`

Map numeric opinion to discrete label from opinion_groups.

**Parameters:**
- `opinion_value`: Numeric opinion in [0, 1]

**Returns:** Discrete label (e.g., "In favor")

#### `_infer_page_agent_opinion(agent_id, article_content, topic_name) -> float`

Infer page agent's opinion on article topic.

**Parameters:**
- `agent_id`: Page agent ID
- `article_content`: Article text
- `topic_name`: Topic to infer opinion about

**Returns:** Opinion value in [0, 1]

### Server API

#### `add_agent_opinion(agent_id, topic_id, opinion, id_interacted_with=None, id_post=None)`

Store agent opinion in database.

**Parameters:**
- `agent_id`: Agent UUID
- `topic_id`: Topic UUID
- `opinion`: Opinion value in [0, 1]
- `id_interacted_with`: Optional agent interaction partner
- `id_post`: Optional post reference

**Returns:** `True` if successful

#### `get_latest_agent_opinion(agent_id, topic_id) -> Optional[float]`

Retrieve agent's most recent opinion on a topic.

**Parameters:**
- `agent_id`: Agent UUID
- `topic_id`: Topic UUID

**Returns:** Opinion value or `None` if not found

#### `get_post_topics(post_id) -> List[str]`

Get all topic IDs associated with a post.

**Parameters:**
- `post_id`: Post UUID

**Returns:** List of topic UUIDs

#### `get_topic_name_from_id(topic_id) -> Optional[str]`

Look up topic name from topic ID.

**Parameters:**
- `topic_id`: Topic UUID

**Returns:** Topic name or `None` if not found

---

## Examples

### Example 1: Agent Updates Opinion After Comment

**Scenario:** Agent A comments on Agent B's post about "AI"

**Initial States:**
- Agent A opinion on AI: 0.3 (Against)
- Agent B opinion on AI: 0.7 (In favor)

**Configuration:**
- epsilon = 0.25
- mu = 0.5
- theta = 0.0

**Process:**

1. Agent A performs COMMENT action
2. Client calculates: |0.7 - 0.3| = 0.4 > 0.25 (exceeds epsilon)
3. Since theta = 0, no update occurs
4. Agent A opinion remains: 0.3

**With Different Parameters (epsilon = 0.5):**

1. |0.7 - 0.3| = 0.4 ≤ 0.5 (within epsilon)
2. New opinion = 0.3 + 0.5 × 0.4 = 0.5
3. Agent A opinion updated to: 0.5 (Neutral)

### Example 2: Cold Start - New Agent Encounters Topic

**Scenario:** Agent C (new) comments on post about "Climate Change"

**Initial State:**
- Agent C has no opinion on "Climate Change"
- Post author opinion: 0.8 (Strongly in favor)

**With cold_start = "neutral":**
- Agent C starts with: 0.5
- Then updated via bounded confidence

**With cold_start = "inherited":**
- Agent C adopts: 0.8
- Then updated via bounded confidence

### Example 3: Page Agent Opinion Inference

**Scenario:** News page posts article about "Electric Vehicles"

**Article Excerpt:**
"Electric vehicles represent the future of transportation, offering zero emissions..."

**Process (LLM Page):**

1. Article topics extracted: ["Electric Vehicles", "Environment"]
2. LLM analyzes article for each topic
3. For "Electric Vehicles":
   - LLM selects: "Strongly in favor"
   - Mapped to: [0.8, 1.0] → 0.9
4. Opinion 0.9 stored in database
5. POST action submitted

**Process (Rule-Based Page):**

1. Article topics extracted: ["Electric Vehicles", "Environment"]
2. For each new topic:
   - Generate random: 0.6234
3. Opinion 0.6234 stored in database
4. POST action submitted

### Example 4: Opinion-Based Content Generation

**Scenario:** LLM agent generates post about "Technology"

**Agent State:**
- Opinion on Technology: 0.75 (In favor)

**Prompt Generated:**
```
You are tech_enthusiast_42, interested in Technology, Innovation, Startups.
Your opinion on this topic is: In favor
Express this viewpoint in your post.

Generate a post about: New smartphone features
```

**Generated Post:**
"Loving the new AI-powered camera features! Technology keeps getting better 📱✨ #innovation"

---

## Best Practices

### 1. Configuration Tuning

**For Opinion Clustering:**
```json
{
  "epsilon": 0.2,
  "mu": 0.5,
  "theta": 0.0
}
```

**For Consensus Formation:**
```json
{
  "epsilon": 0.6,
  "mu": 0.7,
  "theta": 0.0
}
```

**For Polarization:**
```json
{
  "epsilon": 0.25,
  "mu": 0.5,
  "theta": 0.1
}
```

### 2. Opinion Group Design

Choose opinion groups that match your research domain:

**Political Opinions:**
```json
{
  "Strongly left": [0.0, 0.2],
  "Left": [0.2, 0.4],
  "Center": [0.4, 0.6],
  "Right": [0.6, 0.8],
  "Strongly right": [0.8, 1.0]
}
```

**Product Reviews:**
```json
{
  "Very negative": [0.0, 0.2],
  "Negative": [0.2, 0.4],
  "Mixed": [0.4, 0.6],
  "Positive": [0.6, 0.8],
  "Very positive": [0.8, 1.0]
}
```

### 3. Monitoring Opinion Evolution

Track opinion changes over time:

```sql
SELECT 
    agent_id,
    topic_id,
    opinion,
    tid as round_id,
    id_interacted_with,
    id_post
FROM agent_opinion
WHERE agent_id = 'target_agent_id'
ORDER BY tid;
```

### 4. Analyzing Opinion Clusters

Identify opinion clusters:

```sql
SELECT 
    topic_id,
    COUNT(*) as agent_count,
    AVG(opinion) as avg_opinion,
    STDDEV(opinion) as opinion_std
FROM (
    SELECT DISTINCT ON (agent_id, topic_id) 
        agent_id, topic_id, opinion
    FROM agent_opinion
    ORDER BY agent_id, topic_id, tid DESC
) latest_opinions
GROUP BY topic_id;
```

---

## Troubleshooting

### Issue: "Author has no recorded opinion on topic"

**Cause:** Agent posted about topic before opinion was initialized

**Solution:** Opinion inference now happens automatically before POST submission for page agents. For regular agents, ensure initial opinions are provided in `agent_population.json`.

### Issue: Opinion values outside [0, 1] range

**Cause:** Bounded confidence calculation error or data corruption

**Solution:** Check bounded_confidence function parameters and validate input opinions.

### Issue: No opinion updates recorded

**Cause:** Opinion dynamics disabled or client-server communication issue

**Solution:** 
1. Verify `"enabled": true` in configuration
2. Check client logs for opinion calculation
3. Verify server receives `updated_opinions` in ActionDTO

### Issue: LLM opinion inference fails

**Cause:** LLM service unavailable or prompt parsing error

**Solution:**
1. Check LLM service connectivity
2. Verify prompt template in `llm_prompts.json`
3. Falls back to random opinion on error

---

## References

### Academic Literature

1. Hegselmann, R., & Krause, U. (2002). "Opinion dynamics and bounded confidence models, analysis, and simulation." *Journal of Artificial Societies and Social Simulation*, 5(3).

2. Deffuant, G., et al. (2000). "Mixing beliefs among interacting agents." *Advances in Complex Systems*, 3(01n04), 87-98.

3. Lorenz, J. (2007). "Continuous opinion dynamics under bounded confidence: A survey." *International Journal of Modern Physics C*, 18(12), 1819-1838.

### Implementation References

- Bounded Confidence Model: `YSimulator/YClient/opinion_dynamics/confidence_bound.py`
- LLM Opinion Inference: `YSimulator/YClient/LLM_interactions/llm_service.py`
- Database Schema: `YSimulator/YServer/classes/models.py`
- Client Integration: `YSimulator/YClient/client.py`

---

## Version History

- **v1.1** (2026-01-01): Opinion dynamics model selection
  - Added LLM evaluation model
  - Support for model selection via configuration
  - Evaluation scope with neighbors' opinions
  - Validation for LLM-only models
  - Comprehensive test suite

- **v1.0** (2025-12-01): Initial opinion dynamics implementation
  - Bounded confidence model
  - Database tracking
  - Opinion-based interactions
  - Page agent opinion inference
  - LLM integration

---

## Contact & Support

For questions about opinion dynamics implementation:
- Review this documentation
- Check code comments in `opinion_dynamics/` module
- Refer to example configurations in `example/` directory
