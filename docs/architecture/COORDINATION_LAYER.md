# Coordination Layer Documentation

## Overview

The Coordination Layer manages simulation orchestration, client lifecycle, round advancement, and synchronization barriers. Extracted from the monolithic `OrchestratorServer` class in Phase 4 of the server refactoring, these components provide clear separation between orchestration logic and business logic.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    OrchestratorServer                       │
│                    (Uses Coordination)                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Delegates to
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   Coordination Layer                        │
├─────────────────────────────────────────────────────────────┤
│  • ClientManager      - Client lifecycle & heartbeats      │
│  • BarrierHandler     - Synchronization & barrier logic    │
│  • RoundManager       - Time advancement & transitions     │
│  • ArchetypeManager   - Agent archetype transitions        │
└─────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. ClientManager

**Purpose**: Manages client registration, completion tracking, and heartbeat monitoring.

**Responsibilities**:
- Register and deregister simulation clients
- Track client submission status
- Monitor client heartbeats
- Detect and handle stale clients
- Maintain active client count

**Key Methods**:

```python
class ClientManager:
    def register_client(self, client_id: str) -> None:
        """Register a new client."""
        
    def deregister_client(self, client_id: str) -> None:
        """Remove a client from the simulation."""
        
    def mark_client_submitted(self, client_id: str) -> None:
        """Mark that a client has submitted actions."""
        
    def mark_client_completed(self, client_id: str) -> None:
        """Mark that a client has completed the round."""
        
    def heartbeat(self, client_id: str) -> None:
        """Update client heartbeat timestamp."""
        
    def get_stale_clients(self, threshold_seconds: int = 120) -> Set[str]:
        """Get clients that haven't sent heartbeat recently."""
        
    def get_active_clients(self) -> Set[str]:
        """Get all registered, non-completed clients."""
        
    def clear_submitted_clients(self) -> None:
        """Reset submission tracking for new round."""
```

**Usage Example**:

```python
from YSimulator.YServer.coordination.client_manager import ClientManager

# Initialize
client_manager = ClientManager()

# Register clients
client_manager.register_client("client_1")
client_manager.register_client("client_2")

# Track submissions
client_manager.mark_client_submitted("client_1")

# Get active clients
active = client_manager.get_active_clients()
# Returns: {"client_1", "client_2"}

# Check for stale clients
stale = client_manager.get_stale_clients(threshold_seconds=120)

# Clear for next round
client_manager.clear_submitted_clients()
```

---

### 2. BarrierHandler

**Purpose**: Implements dynamic barrier synchronization for distributed simulation.

**Responsibilities**:
- Track client submissions
- Determine when all active clients have submitted
- Decide when to advance simulation
- Handle dynamic client join/leave

**Key Methods**:

```python
class BarrierHandler:
    def check_barrier_and_should_advance(
        self, 
        active_clients: Set[str], 
        submitted_clients: Set[str]
    ) -> bool:
        """
        Check if barrier is satisfied and simulation should advance.
        
        Returns True if all active clients have submitted.
        """
```

**Usage Example**:

```python
from YSimulator.YServer.coordination.barrier_handler import BarrierHandler

# Initialize
barrier = BarrierHandler()

# Check if should advance
active = {"client_1", "client_2", "client_3"}
submitted = {"client_1", "client_2", "client_3"}

should_advance = barrier.check_barrier_and_should_advance(active, submitted)
# Returns: True (all active clients submitted)

# With incomplete submissions
submitted = {"client_1", "client_2"}
should_advance = barrier.check_barrier_and_should_advance(active, submitted)
# Returns: False (client_3 hasn't submitted)
```

**Design Notes**:
- Uses set operations for efficient membership checks
- Handles dynamic barrier (clients can join/leave)
- No hard-coded client count
- Supports client churn mid-simulation

---

### 3. RoundManager

**Purpose**: Manages simulation time advancement and end-of-day processing.

**Responsibilities**:
- Advance simulation time (day/slot)
- Create new simulation rounds
- Trigger end-of-day consolidation
- Invoke interest recomputation
- Coordinate with database for round management

**Key Methods**:

```python
class RoundManager:
    def __init__(
        self, 
        db_adapter: Any, 
        max_slot: int, 
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize round manager.
        
        Args:
            db_adapter: Database adapter for round operations
            max_slot: Maximum slot number per day (e.g., 24 for hourly slots)
            logger: Optional logger instance
        """
        
    def advance_simulation(
        self, 
        current_day: int, 
        current_slot: int,
        recompute_interests_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Advance simulation to next time step.
        
        Returns dict with:
            - 'day': new day
            - 'slot': new slot
            - 'day_completed': bool indicating if day changed
        """
        
    def create_round(
        self, 
        round_id: str, 
        day: int, 
        slot: int
    ) -> None:
        """Create a new simulation round in database."""
```

**Usage Example**:

```python
from YSimulator.YServer.coordination.round_manager import RoundManager

# Initialize with 24 slots per day
round_manager = RoundManager(
    db_adapter=db, 
    max_slot=24
)

# Define interest recomputation callback
def recompute_all_interests():
    print("Recomputing agent interests for new day")
    # ... interest recomputation logic

# Advance simulation
result = round_manager.advance_simulation(
    current_day=1,
    current_slot=23,
    recompute_interests_callback=recompute_all_interests
)

# Result when day completes (slot 23 → 0, day 1 → 2):
# {
#     'day': 2,
#     'slot': 0,
#     'day_completed': True
# }

# Result for mid-day advancement (slot 10 → 11, day stays 1):
# {
#     'day': 1,
#     'slot': 11,
#     'day_completed': False
# }
```

**Time Management**:
- Slots advance linearly: 0, 1, 2, ..., max_slot-1
- After last slot, day increments and slot resets to 0
- End-of-day processing triggered when day changes
- Interest recomputation happens on day transition

---

### 4. ArchetypeManager

**Purpose**: Manages periodic agent archetype transitions based on probability matrices.

**Responsibilities**:
- Check if transitions should occur (every N days)
- Sample new archetypes from probability matrix
- Update agent archetypes in database
- Track last transition day

**Key Methods**:

```python
class ArchetypeManager:
    def __init__(
        self, 
        db_adapter: Any, 
        simulation_config: Dict, 
        transition_interval_days: int = 7,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize archetype manager.
        
        Args:
            db_adapter: Database adapter for user operations
            simulation_config: Simulation configuration with archetype settings
            transition_interval_days: Days between transitions (default: 7)
            logger: Optional logger instance
        """
        
    def should_perform_transitions(
        self, 
        current_day: int, 
        last_transition_day: int
    ) -> bool:
        """Check if enough days have passed for transitions."""
        
    def perform_transitions(self, current_day: int) -> int:
        """
        Perform archetype transitions for all regular agents.
        
        Returns number of agents transitioned.
        """
```

**Usage Example**:

```python
from YSimulator.YServer.coordination.archetype_manager import ArchetypeManager

# Initialize with config
config = {
    "archetypes": {
        "enabled": True,
        "transition_matrix": {
            "echo_chamber": {
                "echo_chamber": 0.8,
                "critical_thinker": 0.1,
                "passive_scroller": 0.1
            },
            # ... other archetype transitions
        }
    }
}

archetype_manager = ArchetypeManager(
    db_adapter=db,
    simulation_config=config,
    transition_interval_days=7
)

# Check if should transition (every 7 days)
should_transition = archetype_manager.should_perform_transitions(
    current_day=8,
    last_transition_day=1
)
# Returns: True (7 days have passed)

# Perform transitions
if should_transition:
    count = archetype_manager.perform_transitions(current_day=8)
    print(f"Transitioned {count} agents")
```

**Transition Logic**:
- Probability-based sampling from transition matrix
- Each archetype has probability distribution to other archetypes
- Regular agents only (page agents excluded)
- Configurable interval (default: 7 days)
- Tracks last transition to prevent duplicate transitions

---

## Integration with OrchestratorServer

### Before Refactoring

```python
class OrchestratorServer:
    def _check_barrier_and_advance(self) -> None:
        # 110+ lines of mixed logic:
        # - Client tracking
        # - Barrier checking
        # - Time advancement
        # - Consolidation
        # - Archetype transitions
        # - Interest recomputation
        
        active_clients = self.registered_clients - self.completed_clients
        if active_clients == self.submitted_clients:
            # ... 50 lines of advancement logic
            if self.slot == self.max_slot - 1:
                # ... 30 lines of end-of-day logic
                self._consolidate_daily_metrics()
            if self.archetypes_enabled and self.day - self.last_archetype_transition_day >= 7:
                # ... 30 lines of archetype logic
```

### After Refactoring

```python
class OrchestratorServer:
    def __init__(self, ...):
        # Initialize coordination components
        self.client_manager = ClientManager()
        self.barrier_handler = BarrierHandler()
        self.round_manager = RoundManager(self.db, self.max_slot)
        self.archetype_manager = ArchetypeManager(
            self.db, 
            self.simulation_config,
            transition_interval_days=7
        )
    
    def _check_barrier_and_advance(self) -> None:
        """Check barrier and advance simulation - now only 25 lines!"""
        # Get active clients
        active_clients = self.client_manager.get_active_clients()
        
        # Check if should advance
        should_advance = self.barrier_handler.check_barrier_and_should_advance(
            active_clients, 
            self.submitted_clients
        )
        
        if should_advance:
            # Clear submission tracking
            self.client_manager.clear_submitted_clients()
            
            # Advance time
            result = self.round_manager.advance_simulation(
                current_day=self.day,
                current_slot=self.slot,
                recompute_interests_callback=self._recompute_all_agent_interests
            )
            
            # Update server state
            self.day = result["day"]
            self.slot = result["slot"]
            
            # Create new round
            self.current_round_id = f"round_{self.day}_{self.slot}"
            self.round_manager.create_round(self.current_round_id, self.day, self.slot)
            
            # Handle archetype transitions
            if result["day_completed"]:
                if self.archetype_manager.should_perform_transitions(
                    self.day, 
                    self.last_archetype_transition_day
                ):
                    count = self.archetype_manager.perform_transitions(self.day)
                    self.logger.info(f"Transitioned {count} agents to new archetypes")
                    self.last_archetype_transition_day = self.day
```

---

## Benefits of Extraction

### 1. Separation of Concerns ✅
- **Client Management**: Isolated in `ClientManager`
- **Synchronization**: Isolated in `BarrierHandler`
- **Time Management**: Isolated in `RoundManager`
- **Agent Lifecycle**: Isolated in `ArchetypeManager`

### 2. Testability ✅
Each component can be tested independently:

```python
# Test ClientManager
def test_client_registration():
    manager = ClientManager()
    manager.register_client("client_1")
    assert "client_1" in manager.get_active_clients()

# Test BarrierHandler
def test_barrier_satisfied():
    handler = BarrierHandler()
    active = {"c1", "c2"}
    submitted = {"c1", "c2"}
    assert handler.check_barrier_and_should_advance(active, submitted) is True

# Test RoundManager
def test_day_advancement():
    manager = RoundManager(mock_db, max_slot=24)
    result = manager.advance_simulation(1, 23)
    assert result["day"] == 2
    assert result["slot"] == 0
    assert result["day_completed"] is True
```

### 3. Maintainability ✅
- Smaller, focused classes
- Clear responsibilities
- Easy to modify without affecting other components
- Reduced method size (110 lines → 25 lines)

### 4. Extensibility ✅
- Easy to add new coordination strategies
- Can plug in different barrier algorithms
- Configurable transition intervals
- Custom advancement callbacks

---

## Configuration

### ClientManager

No configuration required - uses in-memory state.

### BarrierHandler

No configuration required - pure logic component.

### RoundManager

```python
config = {
    "max_slot": 24,  # Slots per day
    # Consolidation handled by database adapter
}
```

### ArchetypeManager

```python
config = {
    "archetypes": {
        "enabled": True,  # Enable/disable transitions
        "transition_matrix": {
            "archetype_A": {
                "archetype_A": 0.7,  # Stay same
                "archetype_B": 0.2,  # Transition to B
                "archetype_C": 0.1   # Transition to C
            },
            # ... other archetypes
        }
    },
    "transition_interval_days": 7  # Days between transitions
}
```

---

## Error Handling

### ClientManager
- Gracefully handles double registration
- Ignores deregistration of non-existent clients
- Thread-safe operations (if needed in future)

### BarrierHandler
- Returns False if no clients active
- Handles empty sets gracefully

### RoundManager
- Logs errors during consolidation
- Continues operation if consolidation fails
- Validates day/slot bounds

### ArchetypeManager
- Skips transitions if disabled in config
- Handles missing transition probabilities
- Logs errors without crashing simulation

---

## Performance Considerations

### ClientManager
- O(1) operations for registration/tracking
- Set-based operations for efficient membership checks
- Minimal memory footprint

### BarrierHandler
- O(n) set comparison where n = number of clients
- No persistent state
- Very fast execution

### RoundManager
- Database operations for round creation
- Consolidation can be expensive (handled asynchronously in future)
- Interest recomputation triggered via callback

### ArchetypeManager
- Bulk database update for transitions
- Probability sampling is O(n) where n = number of agents
- Only runs every N days, not every round

---

## Testing Strategy

### Unit Tests

```python
# ClientManager tests
- test_register_client()
- test_deregister_client()
- test_mark_submitted()
- test_mark_completed()
- test_heartbeat_tracking()
- test_stale_client_detection()
- test_active_clients()

# BarrierHandler tests
- test_barrier_satisfied()
- test_barrier_not_satisfied()
- test_empty_clients()
- test_dynamic_client_join()

# RoundManager tests
- test_advance_slot()
- test_advance_day()
- test_end_of_day_processing()
- test_create_round()
- test_interest_recomputation_callback()

# ArchetypeManager tests
- test_should_perform_transitions()
- test_perform_transitions()
- test_transition_disabled()
- test_probability_sampling()
```

### Integration Tests

```python
# Test full coordination flow
def test_simulation_advancement():
    # Register clients
    # Submit actions
    # Check barrier
    # Advance time
    # Verify state transitions
    # Handle day completion
    # Perform archetype transitions
```

---

## Migration Guide

### From Monolithic to Coordination Layer

**Step 1**: Replace inline client tracking

```python
# Before
self.registered_clients.add(client_id)
self.submitted_clients.add(client_id)

# After
self.client_manager.register_client(client_id)
self.client_manager.mark_client_submitted(client_id)
```

**Step 2**: Replace barrier logic

```python
# Before
active_clients = self.registered_clients - self.completed_clients
if active_clients == self.submitted_clients:
    # advance

# After
active_clients = self.client_manager.get_active_clients()
if self.barrier_handler.check_barrier_and_should_advance(active_clients, self.submitted_clients):
    # advance
```

**Step 3**: Replace time advancement

```python
# Before
self.slot += 1
if self.slot >= self.max_slot:
    self.slot = 0
    self.day += 1
    # consolidation logic

# After
result = self.round_manager.advance_simulation(
    self.day, self.slot, 
    recompute_interests_callback=self._recompute_all_agent_interests
)
self.day = result["day"]
self.slot = result["slot"]
```

**Step 4**: Replace archetype transitions

```python
# Before
if self.archetypes_enabled and self.day - self.last_archetype_transition_day >= 7:
    # 100+ lines of transition logic

# After
if self.archetype_manager.should_perform_transitions(self.day, self.last_archetype_transition_day):
    self.archetype_manager.perform_transitions(self.day)
    self.last_archetype_transition_day = self.day
```

---

## Future Enhancements

### Planned Improvements

1. **Async Consolidation** - Run end-of-day processing in background
2. **Flexible Barriers** - Support partial barriers, timeouts
3. **Advanced Transitions** - Context-aware archetype transitions
4. **Monitoring** - Add metrics for coordination performance
5. **Distributed Coordination** - Support multi-server coordination

### Potential Extensions

- **Custom Barrier Strategies** - Pluggable barrier algorithms
- **Priority Clients** - Some clients can hold up barrier
- **Graceful Degradation** - Continue with timeout if clients stuck
- **State Persistence** - Save/restore coordination state
- **Audit Trail** - Track all coordination events

---

## Troubleshooting

### Common Issues

**Issue**: Simulation not advancing  
**Cause**: Client hasn't submitted or marked completed  
**Solution**: Check `get_active_clients()` and `submitted_clients`

**Issue**: Day not incrementing  
**Cause**: `max_slot` configuration incorrect  
**Solution**: Verify `max_slot` matches intended slots per day

**Issue**: Archetypes not transitioning  
**Cause**: Interval not reached or transitions disabled  
**Solution**: Check `should_perform_transitions()` return value and config

**Issue**: Stale clients accumulating  
**Cause**: Clients not sending heartbeats  
**Solution**: Call `get_stale_clients()` and deregister them

---

## Conclusion

The Coordination Layer successfully extracts complex orchestration logic from the monolithic `OrchestratorServer`, reducing the `_check_barrier_and_advance()` method from 110 lines to 25 lines (77% reduction) and the `_perform_archetype_transitions()` method from 100 lines to 7 lines (93% reduction).

The modular design improves testability, maintainability, and extensibility while maintaining all original functionality. Each component has a single, well-defined responsibility and can be tested and modified independently.

---

**Related Documentation**:
- [Action Processor Framework](ACTION_PROCESSOR_FRAMEWORK.md)
- [Recommendation Engine](RECOMMENDATION_ENGINE.md)
- [Opinion Dynamics Handler](OPINION_DYNAMICS_HANDLER.md)
- [Architecture Overview](ARCHITECTURE.md)
