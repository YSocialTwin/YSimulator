# Adding a Moderator Agent Type with Reinforcement Learning

**Guide Version:** 1.0  
**Last Updated:** January 9, 2026  
**Target Use Case:** Content moderation with adaptive strategy using RL  

## Table of Contents

1. [Overview](#overview)
2. [Moderator Agent Specification](#moderator-agent-specification)
3. [Architecture Design](#architecture-design)
4. [Implementation Pipeline](#implementation-pipeline)
5. [Reinforcement Learning Integration](#reinforcement-learning-integration)
6. [Testing Strategy](#testing-strategy)
7. [Deployment Considerations](#deployment-considerations)
8. [Alternative Approaches](#alternative-approaches)

---

## Overview

This guide describes how to extend YSimulator to support a **Moderator Agent** - a specialized agent type with restricted actions focused on reducing content toxicity. The moderator uses **reinforcement learning** to autonomously develop, evaluate, and adapt moderation strategies.

### Goals

1. **Add New Agent Type:** Implement "moderator" alongside standard agents and page agents
2. **Restrict Actions:** Moderators can only perform specific moderation actions
3. **Goal-Oriented Behavior:** Reduce toxicity of posts in the platform
4. **Adaptive Strategy:** Use RL to learn effective moderation approaches
5. **Support Both Implementations:** Allow LLM-based and rule-based moderators

### Key Requirements

- **Minimal Impact:** Changes should not affect existing agent types
- **Scalability:** Support multiple moderators with different policies
- **Transparency:** Track moderation actions and effectiveness
- **Configurability:** Easy to adjust goals, rewards, and constraints

---

## Moderator Agent Specification

### Agent Characteristics

```python
ModeratorAgent:
    agent_type: "moderator"              # New type identifier
    moderation_goal: "reduce_toxicity"    # Primary objective
    available_actions: [                  # Restricted action set
        "FLAG_POST",                      # Mark post for review
        "WARN_USER",                      # Send warning to user
        "HIDE_POST",                      # Temporarily hide toxic post
        "REQUEST_EDIT",                   # Ask user to edit post
        "READ"                            # Monitor platform content
    ]
    moderation_policy: "adaptive"         # RL-based or "strict" / "lenient"
    effectiveness_metric: "toxicity_reduction_rate"
```

### Moderation Actions

| Action | Description | Impact | Reversible |
|--------|-------------|--------|------------|
| `FLAG_POST` | Mark post for human review | Low visibility | Yes |
| `WARN_USER` | Send warning to author | Notification | N/A |
| `HIDE_POST` | Temporarily hide post | Hidden from feed | Yes (24h) |
| `REQUEST_EDIT` | Ask for content revision | Notification + Pause | Yes |
| `READ` | Monitor content (no action) | None | N/A |

### Success Metrics

The moderator's effectiveness is measured by:

1. **Toxicity Reduction Rate:** % decrease in toxic posts over time
2. **False Positive Rate:** % of incorrectly flagged posts
3. **User Engagement Impact:** Change in platform activity after moderation
4. **Response Time:** Time between toxic post and moderation action

---

## Architecture Design

### Component Overview

```
┌─────────────────────────────────────────────────────┐
│                 YClient (Agent Side)                 │
├─────────────────────────────────────────────────────┤
│  ModeratorAgent                                      │
│  ├─ Agent Profile (type="moderator")                │
│  ├─ Action Restriction Filter                       │
│  ├─ Moderation Action Selector                      │
│  ├─ RL Policy Agent                                 │
│  │  ├─ State Observation (toxicity levels, etc)     │
│  │  ├─ Action Selection (which moderation action)   │
│  │  └─ Reward Calculation (effectiveness tracking)  │
│  └─ Action Generators                               │
│     ├─ FlagGenerator                                │
│     ├─ WarnGenerator                                │
│     ├─ HideGenerator                                │
│     ├─ RequestEditGenerator                         │
│     └─ ModeratorReadGenerator                       │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│               YServer (Orchestrator)                 │
├─────────────────────────────────────────────────────┤
│  ModerationService                                   │
│  ├─ Action Processors                               │
│  │  ├─ FlagPostProcessor                            │
│  │  ├─ WarnUserProcessor                            │
│  │  ├─ HidePostProcessor                            │
│  │  └─ RequestEditProcessor                         │
│  ├─ Toxicity Tracking                               │
│  │  ├─ Platform Toxicity Score                      │
│  │  ├─ User Toxicity History                        │
│  │  └─ Moderation Effectiveness Metrics             │
│  └─ Moderation Event Log                            │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│              Data Storage Layer                      │
├─────────────────────────────────────────────────────┤
│  SQL/Redis                                           │
│  ├─ moderation_actions (table)                      │
│  ├─ user_warnings (table)                           │
│  ├─ post_flags (table)                              │
│  ├─ toxicity_scores (cache)                         │
│  └─ moderation_metrics (cache)                      │
└─────────────────────────────────────────────────────┘
```

### Data Models

#### Moderation Action Schema

```python
# Database table: moderation_actions
ModerationAction:
    id: UUID                      # Unique action identifier
    moderator_id: UUID            # Agent performing moderation
    action_type: str              # FLAG_POST, WARN_USER, etc.
    target_post_id: UUID          # Post being moderated
    target_user_id: UUID          # User being moderated
    toxicity_score: float         # Toxicity score of target (0-1)
    timestamp: datetime           # When action was taken
    reversed: bool                # Whether action was undone
    reversal_reason: str          # Why action was reversed
    effectiveness_score: float    # Post-hoc effectiveness rating
```

#### RL State Representation

```python
# State observed by RL agent
ModerationState:
    # Platform-level features
    recent_toxicity_avg: float         # Avg toxicity last 100 posts
    recent_toxicity_trend: float       # Change over last hour
    active_users_count: int            # Current active users
    
    # Target post features
    post_toxicity_score: float         # Current post toxicity (0-1)
    post_sentiment: dict               # Sentiment breakdown
    author_history_score: float        # Author's avg toxicity
    author_warning_count: int          # Prior warnings
    
    # Moderator features
    recent_actions_count: int          # Actions in last hour
    false_positive_rate: float         # Historical accuracy
    avg_effectiveness: float           # Historical impact
```

---

## Implementation Pipeline

### Phase 1: Foundation (YServer Extensions)

#### Step 1.1: Add Moderation Service

**Location:** `YSimulator/YServer/services/moderation_service.py`

```python
class ModerationService:
    """
    Service for handling content moderation operations.
    Tracks moderation actions, effectiveness, and platform toxicity.
    """
    
    def __init__(self, moderation_repo, post_service, user_service, logger=None):
        self.moderation_repo = moderation_repo
        self.post_service = post_service
        self.user_service = user_service
        self.logger = logger or logging.getLogger(__name__)
    
    def flag_post(self, moderator_id: str, post_id: str, 
                  toxicity_score: float, reason: str) -> bool:
        """Flag a post for human review."""
        # Implementation
        pass
    
    def warn_user(self, moderator_id: str, user_id: str, 
                  warning_message: str) -> bool:
        """Send warning notification to user."""
        pass
    
    def hide_post(self, moderator_id: str, post_id: str, 
                  duration_hours: int = 24) -> bool:
        """Temporarily hide a post from public view."""
        pass
    
    def request_edit(self, moderator_id: str, post_id: str, 
                     suggestions: str) -> bool:
        """Request the author to edit their post."""
        pass
    
    def get_platform_toxicity_metrics(self) -> dict:
        """Calculate current platform toxicity statistics."""
        pass
    
    def get_moderator_effectiveness(self, moderator_id: str, 
                                    time_window_hours: int = 24) -> dict:
        """Calculate moderator's effectiveness metrics."""
        pass
```

**What to implement:**
- CRUD operations for moderation actions
- Toxicity score aggregation
- Effectiveness tracking
- Moderation event logging

#### Step 1.2: Add Moderation Repository

**Location:** `YSimulator/YServer/repositories/moderation_repository.py`

```python
class ModerationRepository(BaseRepository):
    """Repository for moderation data access (SQL + Redis)."""
    
    def store_moderation_action(self, action_data: dict) -> bool:
        """Store moderation action in database."""
        pass
    
    def get_user_warnings(self, user_id: str, days: int = 30) -> List[dict]:
        """Get warning history for a user."""
        pass
    
    def get_flagged_posts(self, status: str = "pending") -> List[dict]:
        """Get posts flagged for review."""
        pass
    
    def update_toxicity_cache(self, post_id: str, score: float):
        """Cache toxicity scores in Redis for fast access."""
        pass
    
    def get_moderation_metrics(self, moderator_id: str = None, 
                               hours: int = 24) -> dict:
        """Get aggregated moderation metrics."""
        pass
```

#### Step 1.3: Add Action Processors

**Location:** `YSimulator/YServer/action_processors/moderation_processor.py`

```python
class ModerationActionProcessor:
    """Process moderation-specific actions from moderator agents."""
    
    def __init__(self, moderation_service, logger=None):
        self.moderation_service = moderation_service
        self.logger = logger
    
    def process_flag_post(self, action: ActionDTO) -> ProcessingResult:
        """
        Process FLAG_POST action.
        
        Args:
            action: ActionDTO with action_type="FLAG_POST"
                   target_post_id, content (reason)
        """
        pass
    
    def process_warn_user(self, action: ActionDTO) -> ProcessingResult:
        """Process WARN_USER action."""
        pass
    
    def process_hide_post(self, action: ActionDTO) -> ProcessingResult:
        """Process HIDE_POST action."""
        pass
    
    def process_request_edit(self, action: ActionDTO) -> ProcessingResult:
        """Process REQUEST_EDIT action."""
        pass
```

#### Step 1.4: Update Database Schema

**SQL Migration:** `scripts/migrations/add_moderation_tables.sql`

```sql
-- Moderation actions table
CREATE TABLE moderation_actions (
    id UUID PRIMARY KEY,
    moderator_id UUID NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    target_post_id UUID,
    target_user_id UUID,
    toxicity_score FLOAT,
    reason TEXT,
    timestamp TIMESTAMP NOT NULL,
    reversed BOOLEAN DEFAULT FALSE,
    reversal_reason TEXT,
    effectiveness_score FLOAT,
    FOREIGN KEY (moderator_id) REFERENCES user_mgmt(id),
    FOREIGN KEY (target_post_id) REFERENCES post(id),
    FOREIGN KEY (target_user_id) REFERENCES user_mgmt(id)
);

-- User warnings table
CREATE TABLE user_warnings (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    moderator_id UUID NOT NULL,
    warning_type VARCHAR(50),
    message TEXT,
    timestamp TIMESTAMP NOT NULL,
    acknowledged BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES user_mgmt(id),
    FOREIGN KEY (moderator_id) REFERENCES user_mgmt(id)
);

-- Post flags table
CREATE TABLE post_flags (
    id UUID PRIMARY KEY,
    post_id UUID NOT NULL,
    moderator_id UUID NOT NULL,
    flag_reason TEXT,
    toxicity_score FLOAT,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, reviewed, dismissed
    timestamp TIMESTAMP NOT NULL,
    reviewed_by UUID,
    review_timestamp TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES post(id),
    FOREIGN KEY (moderator_id) REFERENCES user_mgmt(id)
);

-- Indexes for performance
CREATE INDEX idx_moderation_actions_moderator ON moderation_actions(moderator_id);
CREATE INDEX idx_moderation_actions_timestamp ON moderation_actions(timestamp);
CREATE INDEX idx_user_warnings_user ON user_warnings(user_id);
CREATE INDEX idx_post_flags_status ON post_flags(status);
```

**Redis Keys:**

```python
# Toxicity scores (fast lookup)
"ysim:post:{post_id}:toxicity" -> Float (0-1)

# Platform metrics (aggregated)
"ysim:platform:toxicity:avg" -> Float
"ysim:platform:toxicity:trend" -> Float

# Moderator metrics
"ysim:moderator:{mod_id}:actions:count" -> Integer
"ysim:moderator:{mod_id}:effectiveness" -> Float

# User moderation history
"ysim:user:{user_id}:warnings:count" -> Integer
"ysim:user:{user_id}:warnings:ids" -> Set of warning IDs
```

---

### Phase 2: Client Extensions (YClient)

#### Step 2.1: Update Agent Profile Schema

**Location:** Modify `agent_population.json` schema

```json
{
  "agents": [
    {
      "id": "moderator_001",
      "username": "SafetyBot",
      "agent_type": "moderator",        // NEW: agent type field
      "moderation_config": {             // NEW: moderator-specific config
        "goal": "reduce_toxicity",
        "policy_type": "rl_adaptive",   // or "rule_based" or "llm"
        "action_threshold": 0.7,        // Min toxicity to act
        "max_actions_per_hour": 50,
        "allowed_actions": [
          "FLAG_POST",
          "WARN_USER", 
          "HIDE_POST",
          "REQUEST_EDIT",
          "READ"
        ]
      },
      "rl_config": {                     // RL-specific settings
        "algorithm": "PPO",              // or "DQN", "A3C"
        "learning_rate": 0.0003,
        "exploration_rate": 0.1,
        "reward_discount": 0.99,
        "model_update_frequency": 100   // actions
      }
    }
  ]
}
```

#### Step 2.2: Add Moderator Agent Class

**Location:** `YSimulator/YClient/agents/moderator_agent.py`

```python
class ModeratorAgent:
    """
    Specialized agent for content moderation with RL-based policy.
    
    Responsibilities:
    - Monitor platform content for toxic posts
    - Select appropriate moderation actions
    - Learn from action effectiveness
    - Adapt strategy over time
    """
    
    def __init__(self, agent_profile: dict, rl_policy=None):
        self.agent_id = agent_profile["id"]
        self.agent_type = "moderator"
        self.config = agent_profile["moderation_config"]
        self.rl_policy = rl_policy or self._init_rl_policy(agent_profile["rl_config"])
        
        # State tracking
        self.recent_actions = []
        self.effectiveness_history = []
        self.observation_buffer = []
    
    def observe_content(self, posts: List[dict]) -> ModerationState:
        """
        Observe current platform state and posts.
        
        Returns:
            ModerationState object for RL policy
        """
        pass
    
    def select_action(self, state: ModerationState) -> Optional[ActionDTO]:
        """
        Use RL policy to select best moderation action.
        
        Returns:
            ActionDTO if action needed, None if no action
        """
        pass
    
    def calculate_reward(self, action: ActionDTO, 
                        before_state: ModerationState,
                        after_state: ModerationState) -> float:
        """
        Calculate reward for taken action.
        
        Reward components:
        - Toxicity reduction: +1.0 for each 0.1 decrease
        - False positive penalty: -2.0 if mistakenly flagged
        - User engagement impact: -0.5 if activity drops
        - Efficiency bonus: +0.2 for appropriate action level
        """
        pass
    
    def update_policy(self, state, action, reward, next_state):
        """Update RL policy based on experience."""
        self.rl_policy.update(state, action, reward, next_state)
    
    def _init_rl_policy(self, rl_config: dict):
        """Initialize RL algorithm based on config."""
        pass
```

#### Step 2.3: Add Moderation Action Generators

**Location:** `YSimulator/YClient/action_generators/moderation_generators.py`

```python
class FlagPostGenerator(BaseGenerator):
    """Generate FLAG_POST actions for toxic content."""
    
    def generate(self, agent_data: dict, context: dict) -> Optional[ActionDTO]:
        """
        Generate flag action if post exceeds toxicity threshold.
        
        LLM mode: Ask LLM to assess toxicity and reason
        Rule mode: Use toxicity score from server
        """
        pass


class WarnUserGenerator(BaseGenerator):
    """Generate WARN_USER actions for repeat offenders."""
    
    def generate(self, agent_data: dict, context: dict) -> Optional[ActionDTO]:
        """
        Generate warning for users with multiple toxic posts.
        
        LLM mode: Generate personalized warning message
        Rule mode: Use template warning
        """
        pass


class HidePostGenerator(BaseGenerator):
    """Generate HIDE_POST actions for severe toxicity."""
    
    def generate(self, agent_data: dict, context: dict) -> Optional[ActionDTO]:
        """Hide posts with toxicity > 0.9."""
        pass


class RequestEditGenerator(BaseGenerator):
    """Generate REQUEST_EDIT actions for borderline content."""
    
    def generate(self, agent_data: dict, context: dict) -> Optional[ActionDTO]:
        """
        Request edit for posts with toxicity 0.6-0.8.
        
        LLM mode: Generate constructive suggestions
        Rule mode: Generic edit request
        """
        pass
```

#### Step 2.4: Add Moderation Action Selector

**Location:** `YSimulator/YClient/moderation/action_selector.py`

```python
class ModerationActionSelector:
    """
    Select which moderation action to perform based on:
    - RL policy recommendations
    - Agent configuration constraints
    - Platform state
    """
    
    def __init__(self, moderator_config: dict, rl_policy):
        self.config = moderator_config
        self.rl_policy = rl_policy
        self.action_history = []
    
    def select_action_type(self, state: ModerationState) -> str:
        """
        Select action type using RL policy.
        
        Returns:
            One of: FLAG_POST, WARN_USER, HIDE_POST, REQUEST_EDIT, READ
        """
        # Get RL policy recommendation
        action_probabilities = self.rl_policy.get_action_distribution(state)
        
        # Apply constraints (max actions per hour, allowed actions)
        filtered_actions = self._apply_constraints(action_probabilities)
        
        # Sample action from filtered distribution
        selected_action = self._sample_action(filtered_actions)
        
        return selected_action
    
    def _apply_constraints(self, action_probs: dict) -> dict:
        """Filter actions based on agent constraints."""
        pass
    
    def _sample_action(self, action_probs: dict) -> str:
        """Sample action from probability distribution."""
        pass
```

---

### Phase 3: Reinforcement Learning Integration

#### Step 3.1: Define RL Environment

**Location:** `YSimulator/YClient/rl/moderation_env.py`

```python
import gym
from gym import spaces
import numpy as np

class ModerationEnvironment(gym.Env):
    """
    OpenAI Gym environment for moderation RL training.
    
    State Space:
        - Platform toxicity metrics (3 dims)
        - Target post features (4 dims)
        - Author history (3 dims)
        - Moderator features (3 dims)
        Total: 13-dimensional continuous space
    
    Action Space:
        5 discrete actions:
        0: READ (no action)
        1: FLAG_POST
        2: WARN_USER
        3: HIDE_POST
        4: REQUEST_EDIT
    
    Reward:
        Continuous reward based on toxicity reduction
        and user engagement impact
    """
    
    def __init__(self, server_client, moderator_id: str):
        super().__init__()
        
        self.server_client = server_client
        self.moderator_id = moderator_id
        
        # Define spaces
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(13,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(5)
        
        # Internal state
        self.current_state = None
        self.episode_step = 0
    
    def reset(self):
        """Reset environment to initial state."""
        self.episode_step = 0
        self.current_state = self._get_current_state()
        return self.current_state
    
    def step(self, action: int):
        """
        Execute moderation action and return result.
        
        Returns:
            observation, reward, done, info
        """
        # Execute action through server
        action_dto = self._action_to_dto(action)
        result = self.server_client.submit_action(action_dto)
        
        # Get new state
        next_state = self._get_current_state()
        
        # Calculate reward
        reward = self._calculate_reward(
            self.current_state, action, next_state, result
        )
        
        # Update state
        self.current_state = next_state
        self.episode_step += 1
        
        # Episode termination (after N steps or end of round)
        done = (self.episode_step >= 100) or self._is_round_complete()
        
        info = {
            "toxicity_delta": next_state[0] - self.current_state[0],
            "action_success": result.success
        }
        
        return next_state, reward, done, info
    
    def _get_current_state(self) -> np.ndarray:
        """Query server for current platform state."""
        metrics = self.server_client.get_moderation_state()
        return self._metrics_to_state_vector(metrics)
    
    def _calculate_reward(self, state, action, next_state, result) -> float:
        """
        Reward function for moderation.
        
        Components:
        1. Toxicity reduction: +1.0 per 0.1 decrease in platform avg
        2. False positive penalty: -2.0 if action was wrong
        3. User engagement: -0.5 if platform activity drops > 10%
        4. Action efficiency: +0.2 for using lightest effective action
        """
        reward = 0.0
        
        # Toxicity reduction reward
        toxicity_delta = state[0] - next_state[0]  # Positive if toxicity decreased
        reward += toxicity_delta * 10.0
        
        # False positive penalty
        if result.metadata.get("false_positive", False):
            reward -= 2.0
        
        # Engagement impact
        engagement_delta = (next_state[2] - state[2]) / max(state[2], 1)
        if engagement_delta < -0.1:  # 10% drop
            reward -= 0.5
        
        # Efficiency bonus (prefer lighter actions)
        action_severity = [0, 0.5, 1.0, 2.0, 0.3][action]
        if toxicity_delta > 0 and action_severity < toxicity_delta:
            reward += 0.2
        
        return reward
    
    def _action_to_dto(self, action: int) -> ActionDTO:
        """Convert RL action index to ActionDTO."""
        pass
    
    def _metrics_to_state_vector(self, metrics: dict) -> np.ndarray:
        """Convert metrics dict to state vector."""
        pass
```

#### Step 3.2: Implement RL Algorithms

**Location:** `YSimulator/YClient/rl/policies/`

**Option A: PPO (Recommended)**

```python
# YSimulator/YClient/rl/policies/ppo_policy.py

import torch
import torch.nn as nn
import torch.optim as optim
from stable_baselines3 import PPO

class ModeratorPPOPolicy:
    """
    Proximal Policy Optimization for moderation.
    
    Advantages:
    - Stable training
    - Good sample efficiency
    - Works well with continuous state spaces
    """
    
    def __init__(self, state_dim: int = 13, action_dim: int = 5,
                 learning_rate: float = 0.0003):
        
        self.model = PPO(
            "MlpPolicy",
            env=None,  # Will be set later
            learning_rate=learning_rate,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            verbose=1
        )
    
    def select_action(self, state: np.ndarray, 
                     deterministic: bool = False) -> int:
        """Select action given state."""
        action, _states = self.model.predict(state, deterministic=deterministic)
        return int(action)
    
    def update(self, replay_buffer):
        """Update policy from experience."""
        self.model.learn(total_timesteps=len(replay_buffer))
    
    def save(self, path: str):
        """Save model checkpoint."""
        self.model.save(path)
    
    def load(self, path: str):
        """Load model checkpoint."""
        self.model = PPO.load(path)
```

**Option B: DQN (Alternative)**

```python
# YSimulator/YClient/rl/policies/dqn_policy.py

class ModeratorDQNPolicy:
    """
    Deep Q-Network for moderation.
    
    Advantages:
    - Simple to implement
    - Well-understood
    - Good for discrete actions
    """
    
    def __init__(self, state_dim: int = 13, action_dim: int = 5,
                 learning_rate: float = 0.001):
        
        self.state_dim = state_dim
        self.action_dim = action_dim
        
        # Q-network
        self.q_network = nn.Sequential(
            nn.Linear(state_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 128),
            nn.ReLU(),
            nn.Linear(128, action_dim)
        )
        
        # Target network (for stability)
        self.target_network = copy.deepcopy(self.q_network)
        
        self.optimizer = optim.Adam(self.q_network.parameters(), lr=learning_rate)
        self.replay_buffer = ReplayBuffer(capacity=10000)
        
        # Hyperparameters
        self.epsilon = 0.1  # Exploration rate
        self.gamma = 0.99   # Discount factor
        self.batch_size = 64
    
    def select_action(self, state: np.ndarray, training: bool = True) -> int:
        """Epsilon-greedy action selection."""
        if training and random.random() < self.epsilon:
            return random.randint(0, self.action_dim - 1)
        
        with torch.no_grad():
            q_values = self.q_network(torch.FloatTensor(state))
            return q_values.argmax().item()
    
    def update(self, state, action, reward, next_state, done):
        """Update Q-network using Bellman equation."""
        # Store transition
        self.replay_buffer.add(state, action, reward, next_state, done)
        
        # Sample batch and update
        if len(self.replay_buffer) >= self.batch_size:
            batch = self.replay_buffer.sample(self.batch_size)
            loss = self._compute_loss(batch)
            
            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()
    
    def _compute_loss(self, batch):
        """Compute TD loss."""
        states, actions, rewards, next_states, dones = batch
        
        # Current Q values
        q_values = self.q_network(states).gather(1, actions)
        
        # Target Q values
        with torch.no_grad():
            next_q_values = self.target_network(next_states).max(1)[0]
            target_q_values = rewards + self.gamma * next_q_values * (1 - dones)
        
        # MSE loss
        loss = nn.MSELoss()(q_values, target_q_values.unsqueeze(1))
        return loss
```

#### Step 3.3: Training Pipeline

**Location:** `YSimulator/YClient/rl/training/moderator_trainer.py`

```python
class ModeratorTrainer:
    """
    Train moderator RL policy through simulation.
    
    Training Modes:
    1. Online: Train during live simulation
    2. Offline: Train from recorded moderation logs
    3. Hybrid: Pre-train offline, fine-tune online
    """
    
    def __init__(self, env: ModerationEnvironment, 
                 policy, config: dict):
        self.env = env
        self.policy = policy
        self.config = config
        
        # Training state
        self.episode = 0
        self.total_steps = 0
        self.best_reward = float('-inf')
    
    def train(self, num_episodes: int = 1000, 
             save_frequency: int = 100):
        """
        Train policy for specified episodes.
        
        Args:
            num_episodes: Number of training episodes
            save_frequency: Save checkpoint every N episodes
        """
        for episode in range(num_episodes):
            episode_reward = self._run_episode()
            
            # Logging
            self.logger.info(f"Episode {episode}: reward={episode_reward:.2f}")
            
            # Save checkpoint
            if episode % save_frequency == 0:
                self._save_checkpoint(episode)
            
            # Update best model
            if episode_reward > self.best_reward:
                self.best_reward = episode_reward
                self.policy.save(f"checkpoints/best_model.pt")
    
    def _run_episode(self) -> float:
        """Run one training episode."""
        state = self.env.reset()
        episode_reward = 0.0
        done = False
        
        while not done:
            # Select action
            action = self.policy.select_action(state, training=True)
            
            # Execute action
            next_state, reward, done, info = self.env.step(action)
            
            # Update policy
            self.policy.update(state, action, reward, next_state, done)
            
            # Track metrics
            episode_reward += reward
            state = next_state
            self.total_steps += 1
        
        return episode_reward
    
    def evaluate(self, num_episodes: int = 10) -> dict:
        """
        Evaluate trained policy.
        
        Returns:
            dict with metrics: avg_reward, toxicity_reduction, etc.
        """
        total_reward = 0.0
        toxicity_reductions = []
        
        for _ in range(num_episodes):
            state = self.env.reset()
            episode_reward = 0.0
            done = False
            initial_toxicity = state[0]
            
            while not done:
                # Use deterministic policy for evaluation
                action = self.policy.select_action(state, training=False)
                next_state, reward, done, info = self.env.step(action)
                
                episode_reward += reward
                state = next_state
            
            total_reward += episode_reward
            toxicity_reductions.append(initial_toxicity - state[0])
        
        return {
            "avg_reward": total_reward / num_episodes,
            "avg_toxicity_reduction": np.mean(toxicity_reductions),
            "std_toxicity_reduction": np.std(toxicity_reductions)
        }
```

---

### Phase 4: Integration and Workflow

#### Step 4.1: Update SimulationClient

**Location:** Modify `YSimulator/YClient/client.py`

```python
class SimulationClient:
    
    def __init__(self, config_dir: str, ...):
        # ... existing initialization ...
        
        # NEW: Initialize moderators
        self.moderators = self._init_moderators()
        self.moderation_env = None
        if self.moderators:
            self.moderation_env = ModerationEnvironment(
                server_client=self.server,
                moderator_id=self.moderators[0].agent_id
            )
    
    def _init_moderators(self) -> List[ModeratorAgent]:
        """Initialize moderator agents from population."""
        moderators = []
        
        for agent_data in self.population:
            if agent_data.get("agent_type") == "moderator":
                # Initialize RL policy
                rl_config = agent_data.get("rl_config", {})
                policy = self._create_rl_policy(rl_config)
                
                moderator = ModeratorAgent(agent_data, rl_policy=policy)
                moderators.append(moderator)
        
        return moderators
    
    def _execute_slot(self, slot: int):
        """Execute one simulation time slot."""
        
        # Existing agent execution
        # ... (standard agents perform actions) ...
        
        # NEW: Moderator execution
        if self.moderators:
            self._execute_moderator_actions(slot)
    
    def _execute_moderator_actions(self, slot: int):
        """Execute moderation actions for this time slot."""
        
        for moderator in self.moderators:
            # Observe current state
            state = moderator.observe_content(
                self._get_recent_posts()
            )
            
            # Select moderation action
            action = moderator.select_action(state)
            
            if action:
                # Execute action
                result = self.server.submit_action(action)
                
                # Get new state after action
                next_state = moderator.observe_content(
                    self._get_recent_posts()
                )
                
                # Calculate reward
                reward = moderator.calculate_reward(
                    action, state, next_state
                )
                
                # Update RL policy
                moderator.update_policy(state, action, reward, next_state)
```

#### Step 4.2: Update Server Action Routing

**Location:** Modify `YSimulator/YServer/server.py`

```python
class OrchestratorServer:
    
    def __init__(self, config_dir: str):
        # ... existing initialization ...
        
        # NEW: Initialize moderation service
        self.moderation_service = self._init_moderation_service()
        self.moderation_processor = ModerationActionProcessor(
            self.moderation_service
        )
    
    def submit_action(self, action: ActionDTO) -> ProcessingResult:
        """Route action to appropriate processor."""
        
        # Existing routing for standard actions
        if action.action_type in ["POST", "COMMENT", "LIKE", ...]:
            return self._process_standard_action(action)
        
        # NEW: Route moderation actions
        elif action.action_type in ["FLAG_POST", "WARN_USER", 
                                     "HIDE_POST", "REQUEST_EDIT"]:
            return self.moderation_processor.process(action)
        
        else:
            raise ValueError(f"Unknown action type: {action.action_type}")
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_moderator_agent.py

def test_moderator_initialization():
    """Test moderator agent creation with RL policy."""
    profile = {
        "id": "mod_001",
        "agent_type": "moderator",
        "moderation_config": {...},
        "rl_config": {"algorithm": "PPO"}
    }
    
    moderator = ModeratorAgent(profile)
    assert moderator.agent_type == "moderator"
    assert moderator.rl_policy is not None


def test_action_restriction():
    """Test that moderators only perform allowed actions."""
    moderator = ModeratorAgent(test_profile)
    
    # Should not be able to POST like standard agent
    action = moderator.select_action(mock_state)
    assert action.action_type in ["FLAG_POST", "WARN_USER", 
                                   "HIDE_POST", "REQUEST_EDIT", "READ"]


def test_reward_calculation():
    """Test reward function for toxicity reduction."""
    moderator = ModeratorAgent(test_profile)
    
    # Setup states
    before_state = ModerationState(recent_toxicity_avg=0.8, ...)
    after_state = ModerationState(recent_toxicity_avg=0.6, ...)
    
    action = ActionDTO(action_type="HIDE_POST", ...)
    
    reward = moderator.calculate_reward(action, before_state, after_state)
    assert reward > 0  # Should be positive for toxicity reduction
```

### Integration Tests

```python
# tests/test_moderation_service.py

def test_flag_post_workflow():
    """Test complete flag post workflow."""
    # Setup
    moderation_service = ModerationService(...)
    
    # Flag a post
    result = moderation_service.flag_post(
        moderator_id="mod_001",
        post_id="post_123",
        toxicity_score=0.85,
        reason="Hate speech"
    )
    
    assert result is True
    
    # Verify flag stored
    flags = moderation_service.get_flagged_posts(status="pending")
    assert len(flags) == 1
    assert flags[0]["post_id"] == "post_123"


def test_effectiveness_tracking():
    """Test moderator effectiveness calculation."""
    # Setup: moderate several posts
    # ...
    
    # Calculate effectiveness
    metrics = moderation_service.get_moderator_effectiveness(
        moderator_id="mod_001",
        time_window_hours=24
    )
    
    assert "toxicity_reduction_rate" in metrics
    assert "false_positive_rate" in metrics
    assert "actions_count" in metrics
```

### RL Training Tests

```python
# tests/test_rl_training.py

def test_environment_reset():
    """Test environment initialization."""
    env = ModerationEnvironment(mock_server, "mod_001")
    state = env.reset()
    
    assert len(state) == 13  # State dimension
    assert all(0 <= s <= 1 for s in state)  # Normalized


def test_policy_training():
    """Test RL policy can learn."""
    env = ModerationEnvironment(mock_server, "mod_001")
    policy = ModeratorPPOPolicy()
    trainer = ModeratorTrainer(env, policy, config={})
    
    # Train for short period
    initial_metrics = trainer.evaluate(num_episodes=10)
    trainer.train(num_episodes=100)
    final_metrics = trainer.evaluate(num_episodes=10)
    
    # Policy should improve
    assert final_metrics["avg_reward"] > initial_metrics["avg_reward"]
```

---

## Deployment Considerations

### Configuration Management

**Recommended Setup:**

```json
// moderator_config.json
{
  "moderators": [
    {
      "id": "moderator_001",
      "username": "SafetyBot_Alpha",
      "agent_type": "moderator",
      "implementation": "rl_ppo",  // or "rl_dqn", "rule_based", "llm"
      
      "moderation_config": {
        "goal": "reduce_toxicity",
        "action_threshold": 0.7,
        "max_actions_per_hour": 50,
        "confidence_threshold": 0.8,
        "allowed_actions": ["FLAG_POST", "WARN_USER", "HIDE_POST", "REQUEST_EDIT", "READ"]
      },
      
      "rl_config": {
        "algorithm": "PPO",
        "pretrained_model": "checkpoints/moderator_v1.pt",
        "training_mode": "online",  // or "offline", "frozen"
        "learning_rate": 0.0003,
        "exploration_rate": 0.05,
        "update_frequency": 100
      },
      
      "reward_config": {
        "toxicity_reduction_weight": 10.0,
        "false_positive_penalty": -2.0,
        "engagement_impact_weight": -0.5,
        "efficiency_bonus": 0.2
      }
    }
  ]
}
```

### Monitoring and Observability

**Key Metrics to Track:**

1. **Performance Metrics:**
   - Actions per hour
   - Response time (post creation → moderation)
   - Throughput (posts reviewed per minute)

2. **Effectiveness Metrics:**
   - Platform toxicity trend
   - Toxicity reduction rate
   - False positive rate
   - False negative rate

3. **RL Training Metrics:**
   - Average episode reward
   - Policy loss
   - Value function error
   - Exploration rate over time

**Logging:**

```python
# Log moderation actions
logger.info({
    "event": "moderation_action",
    "moderator_id": moderator.agent_id,
    "action_type": action.action_type,
    "target_post_id": action.target_post_id,
    "toxicity_score": toxicity_score,
    "policy_confidence": confidence,
    "reward": reward
})

# Log effectiveness metrics
logger.info({
    "event": "moderator_effectiveness",
    "moderator_id": moderator.agent_id,
    "time_window_hours": 24,
    "metrics": {
        "toxicity_reduction": 0.15,
        "false_positive_rate": 0.05,
        "actions_count": 127
    }
})
```

### Scaling Considerations

**Multiple Moderators:**

```python
# Distribute moderation load
moderators = [
    ModeratorAgent(profile1, policy=policy1),  # Focuses on hate speech
    ModeratorAgent(profile2, policy=policy2),  # Focuses on spam
    ModeratorAgent(profile3, policy=policy3),  # Focuses on misinformation
]

# Assign posts to moderators based on specialization
for post in posts_to_moderate:
    toxicity_type = classify_toxicity_type(post)
    moderator = select_moderator_by_specialty(toxicity_type)
    moderator.evaluate_post(post)
```

---

## Alternative Approaches

### Approach 1: Rule-Based Moderator

**Simpler, deterministic alternative:**

```python
class RuleBasedModerator:
    """
    Rule-based moderation without RL.
    Useful for baseline or when training data unavailable.
    """
    
    def select_action(self, post: dict) -> str:
        toxicity = post["toxicity_score"]
        author_warnings = post["author_warnings_count"]
        
        # Decision tree
        if toxicity > 0.9:
            return "HIDE_POST"
        elif toxicity > 0.75 and author_warnings > 2:
            return "WARN_USER"
        elif toxicity > 0.6:
            return "REQUEST_EDIT"
        elif toxicity > 0.5:
            return "FLAG_POST"
        else:
            return "READ"  # No action needed
```

### Approach 2: LLM-Based Moderator

**Use language model for contextual moderation:**

```python
class LLMBasedModerator:
    """
    LLM-powered moderation for nuanced understanding.
    Can understand context, sarcasm, cultural references.
    """
    
    def evaluate_post(self, post: dict) -> ActionDTO:
        prompt = f"""
        You are a content moderator. Evaluate this post for toxicity:
        
        Post: "{post['content']}"
        Author history: {post['author_summary']}
        
        Decide on moderation action:
        - NO_ACTION: Post is acceptable
        - FLAG_POST: Borderline, needs review
        - WARN_USER: Violates guidelines
        - HIDE_POST: Severe violation
        - REQUEST_EDIT: Could be acceptable with changes
        
        Explain your reasoning.
        """
        
        response = self.llm.generate(prompt)
        action_type, reasoning = self._parse_llm_response(response)
        
        return ActionDTO(
            agent_id=self.agent_id,
            action_type=action_type,
            content=reasoning,
            target_post_id=post["id"]
        )
```

### Approach 3: Hybrid (RL + LLM)

**Best of both worlds:**

```python
class HybridModerator:
    """
    Use RL for action selection, LLM for generation.
    RL learns when to act, LLM generates appropriate response.
    """
    
    def select_action(self, state: ModerationState) -> ActionDTO:
        # RL selects action type
        action_type = self.rl_policy.select_action(state)
        
        if action_type in ["WARN_USER", "REQUEST_EDIT"]:
            # LLM generates message content
            content = self.llm_generator.generate_message(
                action_type=action_type,
                post=state.target_post,
                context=state
            )
        else:
            content = None
        
        return ActionDTO(
            agent_id=self.agent_id,
            action_type=action_type,
            content=content,
            target_post_id=state.target_post["id"]
        )
```

---

## Summary Checklist

### YServer Changes
- [ ] Create `ModerationService` in `services/moderation_service.py`
- [ ] Create `ModerationRepository` in `repositories/moderation_repository.py`
- [ ] Create `ModerationActionProcessor` in `action_processors/moderation_processor.py`
- [ ] Add database migrations for moderation tables
- [ ] Update `OrchestratorServer.submit_action()` to route moderation actions
- [ ] Add Redis keys for toxicity tracking

### YClient Changes
- [ ] Create `ModeratorAgent` class in `agents/moderator_agent.py`
- [ ] Create moderation action generators in `action_generators/moderation_generators.py`
- [ ] Create `ModerationActionSelector` in `moderation/action_selector.py`
- [ ] Update `SimulationClient._init_moderators()`
- [ ] Update `SimulationClient._execute_slot()` to run moderators
- [ ] Update agent profile schema to support "moderator" type

### RL Integration
- [ ] Create `ModerationEnvironment` in `rl/moderation_env.py`
- [ ] Implement RL policy (PPO or DQN) in `rl/policies/`
- [ ] Create `ModeratorTrainer` in `rl/training/moderator_trainer.py`
- [ ] Add replay buffer and experience storage
- [ ] Implement reward calculation function
- [ ] Add model checkpointing and loading

### Testing
- [ ] Unit tests for moderator agent
- [ ] Unit tests for moderation service
- [ ] Integration tests for action workflow
- [ ] RL environment tests
- [ ] Policy training tests
- [ ] End-to-end simulation test with moderators

### Configuration
- [ ] Add moderator profiles to agent population
- [ ] Create moderator configuration schema
- [ ] Add RL hyperparameters configuration
- [ ] Update documentation with moderator setup

### Monitoring
- [ ] Add logging for moderation actions
- [ ] Add metrics tracking for effectiveness
- [ ] Create dashboard for moderator performance
- [ ] Add alerting for anomalies

---

## Next Steps

1. **Start with Phase 1 (YServer):** Build the foundation by adding moderation service and data layer
2. **Implement Rule-Based Moderator First:** Get basic moderation working before adding RL complexity
3. **Add RL Components Incrementally:** Start with simple DQN, then upgrade to PPO
4. **Train Offline First:** Use historical simulation data before online training
5. **Monitor and Iterate:** Track metrics closely and adjust reward function

---

**Document Version:** 1.0  
**Author:** YSimulator Development Team  
**Date:** January 9, 2026  
**Related Documentation:**
- [EXTENDING.md](EXTENDING.md) - General extension guide
- [AGENT_TYPES.md](../agents/AGENT_TYPES.md) - Agent architecture
- [AGENT_ACTIONS.md](../agents/AGENT_ACTIONS.md) - Action system details
