# Opinion Dynamics Architecture Guide

**Last Updated**: January 8, 2026  
**Phase 4 Integration**: Complete

---

## Overview

YSimulator's opinion dynamics system is split into two complementary packages that work together:

### 1. `opinion_dynamics/` - Opinion Models (Implementation Layer)

**Location**: `YSimulator/YClient/opinion_dynamics/`

**Purpose**: Contains the **actual opinion dynamics algorithms** and mathematical models.

**Files**:
- `confidence_bound.py` - Bounded confidence model implementation
- `llm_evaluation.py` - LLM-based opinion evaluation model
- `utils.py` - Utility functions for opinion classification

**What it does**: Implements the core mathematical algorithms that calculate how opinions change based on interactions.

### 2. `opinion/` - Opinion Management (Orchestration Layer)

**Location**: `YSimulator/YClient/opinion/`

**Purpose**: Provides a **management layer** that orchestrates opinion operations in the simulation.

**Files**:
- `opinion_manager.py` - Main interface for all opinion operations
- `opinion_calculator.py` - Orchestrates opinion update calculations using models from `opinion_dynamics/`
- `opinion_inferencer.py` - Handles opinion inference for page agents
- `opinion_cache.py` - Caching layer for performance optimization

**What it does**: Manages the lifecycle of opinion operations, coordinates between models, handles configuration, and integrates with the simulation client.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      SimulationClient                        │
│                         (client.py)                          │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               │ uses
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                  Opinion Management Layer                    │
│                    (opinion/ package)                        │
├─────────────────────────────────────────────────────────────┤
│  OpinionManager                                              │
│    ├── OpinionCalculator ───────┐                           │
│    ├── OpinionInferencer         │                           │
│    └── OpinionCache              │                           │
└──────────────────────────────────┼──────────────────────────┘
                                   │
                                   │ delegates to
                                   ▼
┌─────────────────────────────────────────────────────────────┐
│              Opinion Dynamics Models Layer                   │
│                (opinion_dynamics/ package)                   │
├─────────────────────────────────────────────────────────────┤
│  bounded_confidence(x, y, epsilon, mu, theta, cold_start)   │
│  llm_evaluation(x, y, text, topic, ...)                     │
│  get_opinion_group(opinion, group_classes)                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Why Two Packages?

### Separation of Concerns

1. **opinion_dynamics/** focuses on **WHAT** - the algorithms
   - Pure mathematical/algorithmic implementations
   - No dependencies on simulation infrastructure
   - Reusable and testable in isolation
   - Can be used independently

2. **opinion/** focuses on **HOW** - the orchestration
   - Integration with simulation infrastructure
   - Configuration management
   - Server communication
   - Caching and performance optimization
   - Lifecycle management

### Benefits

- **Modularity**: Add new opinion models without changing management code
- **Testability**: Test algorithms independently from simulation logic
- **Flexibility**: Swap opinion models easily through configuration
- **Clarity**: Clear separation between algorithm and infrastructure

---

## How to Add a New Opinion Dynamics Model

Follow these steps to add a new opinion dynamics model to YSimulator:

### Step 1: Create the Model Implementation

Create a new file in `YSimulator/YClient/opinion_dynamics/` with your model's algorithm.

**Example**: Creating a "Social Influence" model

```python
# YSimulator/YClient/opinion_dynamics/social_influence.py
"""
Social Influence opinion dynamics model.

This model updates opinions based on weighted social influence from neighbors.
Agents move their opinion towards the weighted average of their neighbors' opinions.
"""

from typing import Optional


def social_influence(
    x: Optional[float],
    neighbors_opinions: list[float],
    influence_weight: float = 0.5,
    cold_start: str = "neutral",
) -> float:
    """
    Update agent's opinion based on neighbors' social influence.
    
    Args:
        x: Agent's current opinion value (None for cold start)
        neighbors_opinions: List of neighbor opinion values
        influence_weight: Weight of social influence (0-1, default 0.5)
        cold_start: Strategy for cold start - "neutral" (0.5) or "random"
    
    Returns:
        float: Updated opinion value in [0, 1] range
    """
    # Handle cold start case
    if x is None:
        if cold_start == "neutral":
            x = 0.5
        elif cold_start == "random":
            import random
            x = random.random()
        else:
            x = 0.5
    
    # If no neighbors, return current opinion
    if not neighbors_opinions:
        return x
    
    # Calculate weighted average of neighbors
    avg_neighbor_opinion = sum(neighbors_opinions) / len(neighbors_opinions)
    
    # Update opinion: move towards average with influence_weight
    new_opinion = x + influence_weight * (avg_neighbor_opinion - x)
    
    # Ensure opinion stays in [0, 1] range
    return max(0.0, min(1.0, new_opinion))
```

### Step 2: Export the Model

Add your model to the `opinion_dynamics/__init__.py`:

```python
# YSimulator/YClient/opinion_dynamics/__init__.py
from .confidence_bound import *
from .llm_evaluation import *
from .social_influence import social_influence  # Add this line
from .utils import get_opinion_group
```

### Step 3: Integrate with OpinionCalculator

Add support for your model in `opinion/opinion_calculator.py`:

```python
# In OpinionCalculator.calculate_updates(), add a new condition:

def calculate_updates(self, agent_id, parent_post_id, parent_post_data, agent_profiles):
    # ... existing code ...
    
    # Calculate new opinion based on selected model
    if model_name == "llm_evaluation":
        new_opinion = self._calculate_llm_evaluation(...)
    elif model_name == "social_influence":  # Add this
        new_opinion = self._calculate_social_influence(
            agent_id=agent_id,
            agent_opinion=agent_opinion,
            topic_id=topic_id,
            params=params,
        )
    else:
        # Use bounded confidence model (default)
        new_opinion = self._calculate_bounded_confidence(...)
    
    # ... rest of code ...


# Add a new helper method:
def _calculate_social_influence(
    self,
    agent_id: str,
    agent_opinion: Optional[float],
    topic_id: str,
    params: dict,
) -> float:
    """
    Calculate opinion update using social influence model.
    
    Args:
        agent_id: Agent UUID
        agent_opinion: Agent's current opinion (None for cold start)
        topic_id: Topic ID
        params: Model parameters (influence_weight, cold_start)
    
    Returns:
        float: Updated opinion value
    """
    from YSimulator.YClient.opinion_dynamics.social_influence import social_influence
    
    # Get neighbors' opinions from server
    import ray
    neighbor_opinions = ray.get(
        self.server.get_neighbors_opinions.remote(
            agent_id, topic_id, client_id=self.client_id
        )
    )
    
    return social_influence(
        x=agent_opinion,
        neighbors_opinions=neighbor_opinions or [],
        influence_weight=params.get("influence_weight", 0.5),
        cold_start=params.get("cold_start", "neutral"),
    )
```

### Step 4: Update Configuration

Add your model to the simulation configuration JSON:

```json
{
  "opinion_dynamics": {
    "enabled": true,
    "model_name": "social_influence",
    "parameters": {
      "influence_weight": 0.5,
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

### Step 5: Add Tests

Create tests for your new model in `YSimulator/tests/test_opinion_dynamics.py`:

```python
class TestSocialInfluence:
    """Tests for the social influence model."""
    
    def test_cold_start_neutral(self):
        """Test cold start with neutral initialization."""
        result = social_influence(
            x=None,
            neighbors_opinions=[0.8],
            cold_start="neutral"
        )
        assert result == 0.5
    
    def test_influence_towards_neighbors(self):
        """Test opinion moves towards neighbors."""
        result = social_influence(
            x=0.3,
            neighbors_opinions=[0.7, 0.8, 0.9],
            influence_weight=0.5
        )
        # Should move towards avg (0.8) from 0.3
        assert result > 0.3
        assert result < 0.8
    
    def test_no_neighbors_no_change(self):
        """Test no change when no neighbors."""
        result = social_influence(
            x=0.5,
            neighbors_opinions=[],
            influence_weight=0.5
        )
        assert result == 0.5
```

### Step 6: Document Your Model

Add documentation for your model in `docs/features/OPINION_DYNAMICS.md`:

```markdown
### Social Influence Model

**Name**: `social_influence`

**Description**: Agents update their opinions based on the weighted average of their neighbors' opinions.

**Parameters**:
- `influence_weight` (float, 0-1): How much neighbors influence the agent (default: 0.5)
- `cold_start` (str): Strategy for agents with no prior opinion - "neutral" or "random"

**Formula**: 
```
new_opinion = current_opinion + influence_weight * (avg_neighbor_opinion - current_opinion)
```

**Use Cases**:
- Social contagion simulations
- Echo chamber studies
- Network-based opinion formation

**Configuration Example**:
```json
{
  "opinion_dynamics": {
    "enabled": true,
    "model_name": "social_influence",
    "parameters": {
      "influence_weight": 0.5,
      "cold_start": "neutral"
    }
  }
}
```
```

---

## Complete Example: Adding "Radical Shift" Model

Here's a complete example of adding a simple "radical shift" model where agents become more extreme over time:

### 1. Create the Model File

```python
# YSimulator/YClient/opinion_dynamics/radical_shift.py
"""
Radical Shift opinion dynamics model.

Agents become more extreme in their opinions over time,
moving away from neutral (0.5) towards the extremes (0 or 1).
"""

from typing import Optional


def radical_shift(
    x: Optional[float],
    shift_rate: float = 0.1,
    cold_start: str = "neutral",
) -> float:
    """
    Update agent's opinion by shifting towards extremes.
    
    Args:
        x: Agent's current opinion value (None for cold start)
        shift_rate: Rate of radicalization (0-1, default 0.1)
        cold_start: Strategy for cold start - "neutral" (0.5)
    
    Returns:
        float: Updated opinion value in [0, 1] range
    """
    # Handle cold start
    if x is None:
        return 0.5 if cold_start == "neutral" else 0.5
    
    # Determine which extreme to move towards
    if x < 0.5:
        # Move towards 0
        new_opinion = x - shift_rate * x
    else:
        # Move towards 1
        new_opinion = x + shift_rate * (1 - x)
    
    # Ensure bounds
    return max(0.0, min(1.0, new_opinion))
```

### 2. Update __init__.py

```python
# YSimulator/YClient/opinion_dynamics/__init__.py
from .confidence_bound import *
from .llm_evaluation import *
from .radical_shift import radical_shift
from .utils import get_opinion_group
```

### 3. Add to OpinionCalculator

```python
# In opinion_calculator.py
elif model_name == "radical_shift":
    from YSimulator.YClient.opinion_dynamics.radical_shift import radical_shift
    new_opinion = radical_shift(
        x=agent_opinion,
        shift_rate=params.get("shift_rate", 0.1),
        cold_start=params.get("cold_start", "neutral"),
    )
```

### 4. Add Tests

```python
def test_radical_shift_moves_to_extreme():
    """Test that opinions move towards extremes."""
    from YSimulator.YClient.opinion_dynamics.radical_shift import radical_shift
    
    # Opinion < 0.5 should move towards 0
    result = radical_shift(x=0.3, shift_rate=0.1)
    assert result < 0.3
    
    # Opinion > 0.5 should move towards 1
    result = radical_shift(x=0.7, shift_rate=0.1)
    assert result > 0.7
```

### 5. Use in Configuration

```json
{
  "opinion_dynamics": {
    "enabled": true,
    "model_name": "radical_shift",
    "parameters": {
      "shift_rate": 0.1,
      "cold_start": "neutral"
    }
  }
}
```

---

## Testing Your Model

### Unit Tests

Test your model in isolation:

```bash
cd /path/to/YSimulator
python -m pytest YSimulator/tests/test_opinion_dynamics.py::TestYourModel -v
```

### Integration Tests

Test your model in the full simulation:

```bash
# Update example configuration to use your model
cd example/your_example
# Edit simulation_config.json to use your model

# Run simulation
python ../../run_server.py --config . &
python ../../run_client.py --config .
```

---

## Best Practices

### When Adding a New Model

1. **Keep models pure**: Models in `opinion_dynamics/` should be pure functions without side effects
2. **Document parameters**: Clearly document all parameters and their valid ranges
3. **Handle edge cases**: Consider cold start, no neighbors, extreme values
4. **Maintain bounds**: Always return opinions in [0, 1] range
5. **Add tests**: Write comprehensive unit tests
6. **Update docs**: Document your model in `OPINION_DYNAMICS.md`

### Model Selection Guidelines

- **Bounded Confidence**: For gradual opinion convergence based on similarity
- **LLM Evaluation**: For natural language reasoning about opinions
- **Social Influence**: For network-based opinion spread
- **Custom Models**: For specific research questions or phenomena

---

## Common Patterns

### Accessing Server Data

```python
# Get neighbors' opinions
import ray
neighbor_opinions = ray.get(
    self.server.get_neighbors_opinions.remote(
        agent_id, topic_id, client_id=self.client_id
    )
)
```

### Using Configuration Parameters

```python
# In your model integration
shift_rate = params.get("shift_rate", 0.1)  # Default to 0.1
cold_start = params.get("cold_start", "neutral")  # Default to neutral
```

### Handling Cold Start

```python
if x is None:
    if cold_start == "neutral":
        x = 0.5
    elif cold_start == "inherited":
        x = y  # Inherit from interlocutor
    elif cold_start == "random":
        x = random.random()
    return x
```

---

## Troubleshooting

### Model Not Found

**Error**: `Unknown model_name in configuration`

**Solution**: Check that:
1. Model is imported in `opinion_dynamics/__init__.py`
2. Model is added to `OpinionCalculator.calculate_updates()`
3. Configuration uses correct model name

### Opinion Values Out of Range

**Error**: Opinion values < 0 or > 1

**Solution**: Always clamp return values:
```python
return max(0.0, min(1.0, new_opinion))
```

### Missing Parameters

**Error**: `KeyError` when accessing parameters

**Solution**: Use `.get()` with defaults:
```python
param = params.get("param_name", default_value)
```

---

## Further Reading

- [OPINION_DYNAMICS.md](OPINION_DYNAMICS.md) - Detailed documentation of existing models
- [CONFIG.md](../configuration/CONFIG.md) - Configuration options
- [EXTENDING.md](../development/EXTENDING.md) - General extension guide

---

**Questions?** Open an issue on GitHub or consult the existing model implementations in `YSimulator/YClient/opinion_dynamics/`.
