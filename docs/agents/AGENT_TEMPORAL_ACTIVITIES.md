# Agent Temporal Activities in YSimulator

This document explains how agents' activity is distributed across time in YSimulator, including activity patterns, temporal controls, and population dynamics.

## Table of Contents
- [Overview](#overview)
- [Activity Profiles](#activity-profiles)
- [Hourly Activity Distribution](#hourly-activity-distribution)
- [Round Actions](#round-actions)
- [Daily Activity Level](#daily-activity-level)
- [Agent Churn](#agent-churn)
- [New Agents](#new-agents)
- [Temporal Coordination](#temporal-coordination)

---

## Overview

YSimulator models realistic temporal patterns of social media activity through multiple mechanisms:

1. **Activity Profiles**: Define time windows when agents are available
2. **Hourly Activity**: Control population-wide activity distribution across hours
3. **Round Actions**: Specify how many actions each agent performs when active
4. **Daily Activity Level**: Determine how frequently agents become active
5. **Churn**: Model agents leaving the platform due to inactivity
6. **New Agents**: Model platform growth with new user arrivals

These mechanisms work together to create realistic, time-varying engagement patterns.

---

## Activity Profiles

### Purpose

Activity profiles define **time windows** during which agents are available to be selected for activity. They model different user schedules (e.g., morning users, evening users, always-on users).

### Configuration

Defined in `simulation_config.json`:

```json
{
  "simulation": {
    "activity_profiles": {
      "Always On": "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23",
      "Morning Active": "6,7,8,9,10,11,12",
      "Evening Active": "17,18,19,20,21,22,23",
      "Weekend Warrior": "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23"
    }
  }
}
```

**Format**:
- **Key**: Profile name (string)
- **Value**: Comma-separated list of hours (0-23) when this profile is active

### Agent Configuration

Assign profiles to agents in `agent_population.json`:

```json
{
  "id": 1,
  "username": "morning_user",
  "activity_profile": "Morning Active"
}
```

### How It Works

```python
# Agent selection process (from client.py)

# 1. Check if agent's profile is active at current slot
profile_name = agent.activity_profile
active_hours = activity_profiles.get(profile_name, list(range(24)))

if slot not in active_hours:
    # Agent is not available at this hour
    skip_agent()
```

**Example**:
- Agent with "Morning Active" profile (hours 6-12)
- Current time slot: 15 (3 PM)
- Result: Agent is **not** available, skipped for this time slot

### Special Cases

**Page Agents**:
- Page agents are **always active** regardless of activity profile
- They bypass the activity profile filter
- This ensures news content is consistently available

**Default Behavior**:
- If an agent has no activity profile specified, defaults to "Always On" (all 24 hours)

### Use Cases

1. **Shift Workers**: Model users with specific work schedules
   ```json
   "Night Shift": "20,21,22,23,0,1,2,3,4,5"
   ```

2. **Business Hours**: Model corporate accounts
   ```json
   "Business Hours": "9,10,11,12,13,14,15,16,17"
   ```

3. **Regional Patterns**: Model timezone-specific activity
   ```json
   "Asian Hours": "0,1,2,3,4,5,6,7,8"
   "European Hours": "8,9,10,11,12,13,14,15,16"
   "US Hours": "16,17,18,19,20,21,22,23"
   ```

---

## Hourly Activity Distribution

### Purpose

Hourly activity controls the **population-wide percentage** of agents that should be active during each hour, creating realistic daily engagement curves.

### Configuration

Defined in `simulation_config.json`:

```json
{
  "simulation": {
    "hourly_activity": {
      "0": 0.023,  "1": 0.021,  "2": 0.02,   "3": 0.02,
      "4": 0.018,  "5": 0.017,  "6": 0.017,  "7": 0.018,
      "8": 0.02,   "9": 0.02,   "10": 0.021, "11": 0.022,
      "12": 0.024, "13": 0.027, "14": 0.03,  "15": 0.032,
      "16": 0.032, "17": 0.032, "18": 0.032, "19": 0.031,
      "20": 0.03,  "21": 0.029, "22": 0.027, "23": 0.025
    }
  }
}
```

**Format**:
- **Key**: Hour string ("0" through "23")
- **Value**: Probability (0.0 to 1.0) representing percentage of eligible agents to activate

**Default**: If not specified, defaults to 0.04 (4%) for all hours

### How It Works

```python
# Activity selection process (from client.py)

# 1. Get probability for current hour
hourly_prob = hourly_activity.get(str(slot), 0.04)

# 2. Filter agents by activity_profile (get eligible agents)
eligible_agents = [a for a in agents if slot in a.activity_profile_hours]

# 3. Calculate number to activate
num_to_activate = int(len(eligible_agents) * hourly_prob)

# 4. Randomly select agents
active_agents = random.sample(eligible_agents, num_to_activate)
```

### Example Distribution

The default configuration creates a realistic daily engagement pattern:

| Time Period | Hours | Avg Probability | Pattern |
|-------------|-------|-----------------|---------|
| **Night** | 0-5 | 0.019 | Low activity (sleep hours) |
| **Morning** | 6-11 | 0.020 | Gradual increase (commute, work start) |
| **Afternoon** | 12-16 | 0.028 | Peak activity (lunch, breaks) |
| **Evening** | 17-21 | 0.031 | High activity (after work) |
| **Late Evening** | 22-23 | 0.026 | Moderate activity (before bed) |

### Interaction with Activity Profiles

The two mechanisms work together:

1. **Activity Profile** = Eligible agents (who *can* be active)
2. **Hourly Activity** = Selection percentage (how many *are* active)

**Example Scenario**:
```
Total agents: 1000
Current slot: 18 (6 PM)
Hourly activity for slot 18: 0.032 (3.2%)

Step 1: Filter by activity_profile
- Agents with profiles active at hour 18: 800 agents

Step 2: Calculate number to activate
- 800 × 0.032 = 25.6 → 25 agents

Step 3: Random selection
- Randomly select 25 agents from the 800 eligible agents
```

### Customization Examples

**Uniform Distribution** (all hours equally active):
```json
{
  "hourly_activity": {
    "0": 0.04, "1": 0.04, "2": 0.04, ..., "23": 0.04
  }
}
```

**Peak Hours** (emphasize specific times):
```json
{
  "hourly_activity": {
    "12": 0.08,  // Lunch break
    "18": 0.10,  // Evening peak
    "20": 0.09   // Prime time
  }
}
```

**Night Owl Pattern**:
```json
{
  "hourly_activity": {
    "0": 0.05, "1": 0.05, "2": 0.04,   // Late night
    "10": 0.02, "11": 0.02, "12": 0.02,  // Low morning
    "22": 0.06, "23": 0.06   // Active evening
  }
}
```

---

## Round Actions

### Purpose

`round_actions` specifies **how many actions** an agent performs during a single time slot when they are active.

### Configuration

Defined per agent in `agent_population.json`:

```json
{
  "id": 1,
  "username": "high_activity_user",
  "round_actions": 5
}
```

**Values**: Integer (typically 1-5)
- **1**: Very light activity (minimal engagement)
- **2-3**: Moderate activity (typical user)
- **4-5**: High activity (power user)

### How It Works

```python
# Action execution (from client.py)

for agent in active_agents:
    num_actions = agent.round_actions
    
    for _ in range(num_actions):
        # 1. Select action type based on archetype and likelihood
        action_type = select_action_for_agent(agent)
        
        # 2. Execute action (LLM or rule-based)
        action = generate_action(agent, action_type)
        
        # 3. Submit to server
        submit_action(action)
```

### Special Cases

**Page Agents**:
- Page agents override `round_actions`
- Perform **at most 1 action** per time slot (0 or 1)
- This prevents news flooding

```python
if agent.is_page == 1:
    num_actions = random.randint(0, 1)  # 0 or 1 action
```

### Interaction with Other Variables

**Combined with Daily Activity Level**:
- `daily_activity_level`: How often agent is selected
- `round_actions`: How much they do when selected

**Example**:
```json
{
  "daily_activity_level": 2,  // Selected ~2 times per day
  "round_actions": 3           // Performs 3 actions when selected
}
```
Result: ~6 actions per day

### Use Cases

**Power Users** (broadcasters, influencers):
```json
{
  "archetype": "Broadcaster",
  "round_actions": 5,
  "daily_activity_level": 4
}
```

**Casual Users** (lurkers, validators):
```json
{
  "archetype": "Validator",
  "round_actions": 1,
  "daily_activity_level": 1
}
```

**Moderate Users** (typical engagement):
```json
{
  "round_actions": 3,
  "daily_activity_level": 2
}
```

---

## Daily Activity Level

### Purpose

`daily_activity_level` is a convenience variable that influences how frequently an agent is selected for activity. It's a simplified way to control overall engagement without managing complex probability distributions.

### Configuration

Defined per agent in `agent_population.json`:

```json
{
  "id": 1,
  "username": "frequent_user",
  "daily_activity_level": 4
}
```

**Values**: Integer (typically 1-4)
- **1**: Low frequency (~1-2 times per day)
- **2**: Moderate frequency (~3-5 times per day)
- **3**: High frequency (~6-10 times per day)
- **4**: Very high frequency (~10-15 times per day)

### Relationship to Other Variables

`daily_activity_level` is a **conceptual variable** that helps configure agent profiles. It interacts with:
- `activity_profile`: Time windows when agent can be active
- `hourly_activity`: Population-wide activity distribution
- `round_actions`: Actions performed when active

**Note**: `daily_activity_level` doesn't directly control selection probability in code. Instead, it guides configuration decisions about `hourly_activity` and agent distribution.

### Typical Configurations

**Low Activity User** (daily_activity_level: 1):
```json
{
  "activity_profile": "Evening Active",
  "round_actions": 1,
  "daily_activity_level": 1
}
```
Expected: Active ~1-2 time slots per day, 1 action each → ~1-2 actions/day

**Moderate Activity User** (daily_activity_level: 2):
```json
{
  "activity_profile": "Morning Active",
  "round_actions": 2,
  "daily_activity_level": 2
}
```
Expected: Active ~3-4 time slots per day, 2 actions each → ~6-8 actions/day

**High Activity User** (daily_activity_level: 3):
```json
{
  "activity_profile": "Always On",
  "round_actions": 3,
  "daily_activity_level": 3
}
```
Expected: Active ~8-10 time slots per day, 3 actions each → ~24-30 actions/day

**Power User** (daily_activity_level: 4):
```json
{
  "activity_profile": "Always On",
  "round_actions": 4,
  "daily_activity_level": 4
}
```
Expected: Active ~12-15 time slots per day, 4 actions each → ~48-60 actions/day

---

## Agent Churn

### Purpose

Churn models agents leaving the platform due to prolonged inactivity, simulating realistic user attrition.

### Configuration

Defined in `simulation_config.json`:

```json
{
  "agents": {
    "churn": {
      "enabled": true,
      "churn_probability": 0.05,
      "inactivity_threshold": 7,
      "churn_percentage": 0.2
    }
  }
}
```

**Parameters**:
- `enabled` (boolean): Enable/disable churn mechanism
- `churn_probability` (0.0-1.0): Probability that an inactive agent will churn
- `inactivity_threshold` (integer): Days without activity before considered inactive
- `churn_percentage` (0.0-1.0): Percentage of inactive agents to evaluate each day

### How It Works

Churn evaluation occurs **at the end of each simulation day** (last time slot):

```python
# Churn evaluation process (from client.py)

# 1. Track agent activity
if agent_was_active:
    last_active_day[agent_id] = current_day

# 2. At end of day, identify inactive agents
days_inactive = current_day - last_active_day[agent_id]
inactive_agents = [a for a in agents if days_inactive >= inactivity_threshold]

# 3. Randomly select candidates for evaluation
num_to_evaluate = int(len(inactive_agents) * churn_percentage)
candidates = random.sample(inactive_agents, num_to_evaluate)

# 4. For each candidate, roll probability
for agent in candidates:
    if random.random() < churn_probability:
        # Mark as churned
        agent.left_on = current_round_id
        # Exclude from future activity
        active_population.remove(agent)
```

### Database Fields

**`last_active_day`**: Tracks last simulation day agent was active
- Updated when agent is selected for activity
- Used to calculate inactivity duration

**`left_on`**: Round ID when agent churned
- NULL = agent is active
- Set to current Round UUID when churned
- Used to filter out churned agents

### Example Scenario

**Configuration**:
```json
{
  "churn_probability": 0.1,
  "inactivity_threshold": 5,
  "churn_percentage": 0.2
}
```

**Simulation**:
```
Day 1-5: Agent "user_123" is active
Day 6-10: Agent "user_123" is inactive (no activity)
Day 11: Churn evaluation
  - Days inactive: 5 (meets threshold)
  - Identified as inactive
  - 20% of inactive agents selected as candidates
  - "user_123" is selected (random chance)
  - Probability check: random() < 0.1 → passes (10% chance)
  - Result: Agent churned (left_on = day_11_round_id)
Day 12+: Agent no longer eligible for activity selection
```

### Performance Optimization

Churn uses **batch operations** to minimize server calls:

```python
# Batch churn update
churned_agent_ids = [list of churned agent IDs]
ray.get(server.batch_update_churn.remote(churned_agent_ids, round_id))

# Previous approach: ~80 individual server calls per day
# New approach: 1 batch call per day
# Performance gain: ~98% reduction
```

### Preventing Churn

To prevent specific agents from churning:
- Ensure they are selected for activity regularly
- Set `activity_profile: "Always On"` for critical agents
- Increase `hourly_activity` probabilities
- Consider setting `daily_activity_level: 4` for key agents

### Disabling Churn

To disable churn entirely:
```json
{
  "agents": {
    "churn": {
      "enabled": false
    }
  }
}
```

Or omit the `churn` section completely.

---

## New Agents

### Purpose

New agents model platform growth by dynamically adding agents during simulation, representing new user sign-ups.

### Configuration

Defined in `simulation_config.json`:

```json
{
  "agents": {
    "new_agents": {
      "enabled": true,
      "probability_new_agents": 0.1,
      "percentage_new_agents": 0.05
    }
  }
}
```

**Parameters**:
- `enabled` (boolean): Enable/disable new agent creation
- `probability_new_agents` (0.0-1.0): Probability each slot will be filled
- `percentage_new_agents` (0.0-1.0): Percentage of non-churned agents for slot calculation

### How It Works

New agent creation occurs **at the end of each simulation day**:

```python
# New agent creation process (from client.py)

# 1. Count non-churned agents
non_churned = [a for a in agents if a.left_on is None]
num_non_churned = len(non_churned)

# 2. Calculate available slots
num_slots = int(num_non_churned * percentage_new_agents)

# 3. For each slot, roll probability
new_agents = []
for _ in range(num_slots):
    if random.random() < probability_new_agents:
        # Create new agent
        template = random.choice(non_churned)
        new_agent = create_new_agent_from_template(template)
        new_agents.append(new_agent)

# 4. Batch register with server
if new_agents:
    ray.get(server.register_agents.remote(new_agents))
    
# 5. Update agent_population.json for persistence
update_agent_population_file(new_agents)
```

### Agent Creation Details

**Template Selection**:
- Randomly select an existing non-churned agent as template
- Copy all attributes except `id`, `username`, `joined_on`

**Name Generation**:
- Uses Faker library for realistic names
- Gender-aligned based on template agent's gender
- Spaces and periods replaced with underscores
- Uniqueness ensured by checking existing usernames

**Example**:
```python
# Template agent
template = {
    "gender": "female",
    "archetype": "Broadcaster",
    "llm": true,
    "round_actions": 3
}

# Generated new agent
new_agent = {
    "id": "new-uuid-generated",
    "username": "Jennifer_Smith",  # Generated by Faker
    "joined_on": "current-round-uuid",
    "gender": "female",  # From template
    "archetype": "Broadcaster",  # From template
    "llm": true,  # From template
    "round_actions": 3  # From template
}
```

### Database Fields

**`joined_on`**: Round ID when agent joined
- Set to current Round UUID when created
- Used to track new agent cohorts

**`left_on`**: Explicitly set to NULL
- New agents are not churned
- Ensures they are included in active population

### Example Scenario

**Configuration**:
```json
{
  "probability_new_agents": 0.5,
  "percentage_new_agents": 0.05
}
```

**Simulation**:
```
Population: 100 agents, 10 churned, 90 non-churned

Day 1 End:
  - Calculate slots: int(90 * 0.05) = 4 slots
  - Roll probability for each slot (50% each):
    - Slot 1: random() < 0.5 → Yes, create agent
    - Slot 2: random() < 0.5 → No
    - Slot 3: random() < 0.5 → Yes, create agent
    - Slot 4: random() < 0.5 → No
  - Result: 2 new agents created
  - Generate names: "John_Doe", "Jane_Smith"
  - Batch register with server
  - Update agent_population.json

Day 2+: New agents participate like original agents
  - Population now: 92 non-churned agents
  - New slots calculated: int(92 * 0.05) = 4 slots
```

### Performance Optimization

New agents use **batch operations**:

```python
# Batch registration
new_agent_profiles = [list of AgentProfile objects]
ray.get(server.register_agents.remote(new_agent_profiles))

# Previous approach: ~36 individual server calls per day
# New approach: 1 batch call per day
# Performance gain: ~97% reduction
```

### Persistence

New agents are automatically appended to `agent_population.json`:

```json
{
  "agents": [
    // ... existing agents ...
    {
      "id": "new-agent-uuid",
      "username": "Generated_Name",
      "joined_on": "round-uuid",
      // ... all other fields from template ...
    }
  ]
}
```

This ensures new agents persist across simulation runs.

### Disabling New Agents

To disable new agent creation:
```json
{
  "agents": {
    "new_agents": {
      "enabled": false
    }
  }
}
```

Or omit the `new_agents` section completely.

---

## Combined Churn and New Agents

### Population Dynamics

Use both features together for realistic population evolution:

```json
{
  "agents": {
    "churn": {
      "enabled": true,
      "churn_probability": 0.05,
      "inactivity_threshold": 7,
      "churn_percentage": 0.2
    },
    "new_agents": {
      "enabled": true,
      "probability_new_agents": 0.1,
      "percentage_new_agents": 0.05
    }
  }
}
```

### Population Trends

The balance of churn and new agent rates determines population trajectory:

**Declining Population**:
- High churn + low new = shrinking user base
```json
{
  "churn": {"churn_probability": 0.2, "churn_percentage": 0.3},
  "new_agents": {"probability_new_agents": 0.05, "percentage_new_agents": 0.02}
}
```

**Growing Population**:
- Low churn + high new = expanding user base
```json
{
  "churn": {"churn_probability": 0.01, "churn_percentage": 0.1},
  "new_agents": {"probability_new_agents": 0.3, "percentage_new_agents": 0.08}
}
```

**Stable Population with Turnover**:
- Balanced rates = constant size with member changes
```json
{
  "churn": {"churn_probability": 0.05, "churn_percentage": 0.2},
  "new_agents": {"probability_new_agents": 0.1, "percentage_new_agents": 0.05}
}
```

### Example Simulation

**Initial State**: 1000 agents

**Day 1**:
- Churn: 10 agents leave (1% of population)
- New: 5 agents join (0.5% of population)
- End: 995 agents (-0.5% net)

**Day 2**:
- Churn: 8 agents leave
- New: 6 agents join
- End: 993 agents

**Day 30**:
- Total churned: 280 agents (28% of original)
- Total new: 150 agents (15% of original)
- Population: 870 agents (-13% net)
- Composition: 72% original, 28% new

---

## Temporal Coordination

### Simulation Time Structure

YSimulator uses a hierarchical time structure:

```
Day 1
  ├─ Slot 0 (hour 0)
  ├─ Slot 1 (hour 1)
  ├─ ...
  └─ Slot 23 (hour 23)
Day 2
  ├─ Slot 0
  ├─ ...
  └─ Slot 23
```

**Configuration**:
```json
{
  "simulation": {
    "num_days": 30,
    "num_slots_per_day": 24
  }
}
```

### Time Slot Execution

Each time slot follows this sequence:

1. **Agent Selection**: Based on activity_profile and hourly_activity
2. **Action Execution**: Each agent performs round_actions actions
3. **Reply Processing**: Agents reply to mentions (if applicable)
4. **Barrier Synchronization**: Client waits for other clients
5. **Heartbeat**: Client signals liveness to server
6. **Time Advancement**: Server advances to next slot

### End-of-Day Operations

At the end of each day (slot 23 → day+1), additional operations occur:

1. **Daily Follow Evaluation**: Active agents evaluate new follows
2. **Churn Evaluation**: Inactive agents may leave platform
3. **New Agent Creation**: New agents join platform
4. **Interest Recomputation**: Sliding window updates (if interests enabled)
5. **Redis Consolidation**: Move data from Redis to SQL (if Redis enabled)

**Order of Operations**:
```python
# End of day sequence (from client.py)
def _end_of_day_operations(day):
    # 1. Daily follows
    evaluate_daily_follows(active_agents_today)
    
    # 2. Churn
    if churn_enabled:
        evaluate_churn(inactive_agents)
    
    # 3. New agents
    if new_agents_enabled:
        create_new_agents()
    
    # 4. Interest recomputation (server-side)
    server.recompute_all_agent_interests()
    
    # 5. Redis consolidation (server-side)
    if redis_enabled:
        server.consolidate_day(day)
```

### Multi-Client Coordination

In multi-client scenarios, temporal coordination ensures all clients progress together:

**Barrier Mechanism**:
- Clients submit completion after each slot
- Server waits for all active clients before advancing time
- Stale clients (no heartbeat) are automatically removed

**Heartbeat System**:
- Clients send heartbeat every `heartbeat_interval` seconds (default: 5)
- Server tracks last heartbeat timestamp
- Clients exceeding timeout removed from active set

See [ARCHITECTURE.md](ARCHITECTURE.md#coordination-mechanisms) for details.

---

## Configuration Examples

### Balanced Population

Moderate activity with stable population:

```json
{
  "simulation": {
    "num_days": 30,
    "num_slots_per_day": 24,
    "activity_profiles": {
      "Always On": "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23",
      "Morning Active": "6,7,8,9,10,11,12",
      "Evening Active": "17,18,19,20,21,22,23"
    },
    "hourly_activity": {
      "12": 0.05, "18": 0.06, "20": 0.05
    }
  },
  "agents": {
    "churn": {
      "enabled": true,
      "churn_probability": 0.03,
      "inactivity_threshold": 7,
      "churn_percentage": 0.15
    },
    "new_agents": {
      "enabled": true,
      "probability_new_agents": 0.08,
      "percentage_new_agents": 0.04
    }
  }
}
```

### High Activity Simulation

Emphasis on peak engagement times:

```json
{
  "simulation": {
    "hourly_activity": {
      "8": 0.08, "12": 0.10, "18": 0.12, "20": 0.10
    }
  },
  "agents": [
    {
      "username": "power_user",
      "activity_profile": "Always On",
      "daily_activity_level": 4,
      "round_actions": 5
    }
  ]
}
```

### Growing Platform

Simulate platform growth phase:

```json
{
  "agents": {
    "churn": {
      "enabled": true,
      "churn_probability": 0.01,
      "inactivity_threshold": 10,
      "churn_percentage": 0.1
    },
    "new_agents": {
      "enabled": true,
      "probability_new_agents": 0.25,
      "percentage_new_agents": 0.08
    }
  }
}
```

---

## Related Documentation

- **[AGENT_TYPES.md](AGENT_TYPES.md)**: Agent types, archetypes, and profile variables
- **[AGENT_ACTIONS.md](AGENT_ACTIONS.md)**: Available actions and selection mechanisms
- **[CONFIG.md](CONFIG.md)**: Complete configuration reference
- **[ARCHITECTURE.md](ARCHITECTURE.md)**: System architecture and coordination
- **[INTERESTS.md](INTERESTS.md)**: Interest tracking and evolution
- **[OPINION_DYNAMICS.md](OPINION_DYNAMICS.md)**: Opinion modeling

---

**Last Updated**: January 2, 2026  
**Version**: 2.0
