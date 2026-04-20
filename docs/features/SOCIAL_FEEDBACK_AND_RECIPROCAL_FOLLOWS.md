# Social Feedback And Reciprocal Follows

Recent YSimulator updates added two social feedback mechanisms that sit on top of the existing distributed action pipeline:

- stress/reward-aware interaction updates with optional churn
- reciprocal follow and unfollow decisions, including secondary follows

These features are implemented across the Ray client/server split without changing the central contract: the client evaluates behavior and any LLM decisions, while the server owns persistence and graph state.

## Stress/Reward In HPC

The HPC stack now supports the same `stress_reward` configuration shape used by the web-backed experiments:

```json
{
  "stress_reward": {
    "enabled": true,
    "backward_rounds": 24,
    "system": {
      "events": {},
      "coupling": {},
      "churn": {
        "enabled": false
      }
    }
  }
}
```

The server receives this block through `run_server.py`, which now forwards top-level stress/reward settings into the server-side simulation config. On the client side, the `StressRewardSystem` refreshes the current aggregate state before an agent acts. If churn is enabled in `stress_reward.system.churn`, the client computes a churn probability from the aggregate `stress` and `reward` values and can mark the agent as churned through the normal lifecycle path.

Directed actions can then create variation updates for the target user. The HPC implementation supports reaction, comment, share, and moderation-related deltas through the shared stress/reward logic.

### Round Windowing

Unlike the web simulations, HPC round ids are UUIDs. Aggregate reconstruction therefore cannot rely on numeric `tid` ordering alone. The server-side implementation resolves the `rounds` rows and computes time windows using the actual `(day, hour)` ordering referenced by each UUID round id.

That means:

- backward windows are determined from real simulation time, not UUID order
- same-round variations after an aggregate checkpoint are still included
- aggregate reconstruction remains correct even when round ids are sparse or non-sequential

## Reciprocal Follow And Unfollow

YSimulator now supports follow-back and unfollow-back evaluation after successful follow or unfollow actions.

The main client-side parameter is:

- `agents.probability_of_follow_back`

If the probability gate passes, the target user may create or remove the reciprocal edge. Rule-based agents use only the configured probability. LLM-backed agents can inspect the initiating user’s profile before deciding.

This applies to:

- direct follow/unfollow actions
- secondary follow actions triggered after content interactions

The `SecondaryFollowProcessor` feeds into the same reciprocal-follow path, so secondary follows are no longer a special case.

Before applying the reciprocal edge, the client asks the server whether the reverse edge already exists. That avoids duplicate follow rows and invalid reciprocal unfollows.

## Why This Matters

These additions make the HPC simulator better suited for experiments where user state and network structure evolve together. Stress/reward updates connect interpersonal interactions to measured user outcomes, while reciprocal follow handling makes relationship changes more realistic in distributed runs with multiple clients.
