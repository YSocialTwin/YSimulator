# Agent Memory

YSimulator supports the same experiment-level memory contract used by the
microblogging and forum clients, but it preserves YSimulator's Ray-based
architecture:

- memory runs entirely inside the client actor
- only the server actor reads or writes the database
- only the client actor talks to LLM and embedding backends

## Architecture

Memory is integrated through `/Users/rossetti/PycharmProjects/YWeb/external/YSimulator/YSimulator/YClient/memory_runtime.py`.

The memory manager:

- builds one memory engine per LLM-enabled agent
- converts UUID-based YSimulator identifiers to stable integer surrogates expected by `yclient-memory`
- reads post, user, round, and thread context through server actor RPCs
- injects memory context into post, reply, share, and browse prompts
- records memory events only after actions are successfully submitted to the server

This avoids violating the client/server contract and keeps the existing Ray
execution model intact.

## Supported Actions

Memory currently influences the same interaction classes already supported in
the Flask-based clients:

- `POST`
- `SHARE`
- `COMMENT`
- read/search style browsing prompts
- vote/reaction events

The client records:

- authored post events
- comment events with thread context
- vote events
- maintenance ticks after each slot

## Configuration Contract

Memory lives under the client `agents` section and mirrors the top-level YSocial
contract used for other experiment types.

Minimal example:

```json
{
  "agents": {
    "memory_enabled": true,
    "memory_backend": "hybrid_semantic",
    "memory_prompt_mode": "subtle_timeline",
    "memory_embedding_model": "embeddinggemma",
    "memory_semantic_enabled": true,
    "memory_search_k": 8,
    "memory_search_max_chars": 900,
    "memory_reply_context_max_chars": 220
  }
}
```

Full supported keys:

- `memory_enabled`
- `memory_backend`
- `memory_prompt_mode`
- `memory_vote_signal_only`
- `memory_reply_context_max_chars`
- `memory_cross_thread_callback_min_score`
- `memory_high_affect_enabled`
- `memory_high_affect_rule_threshold`
- `memory_high_affect_uncertain_low`
- `memory_high_affect_uncertain_high`
- `memory_high_affect_search_k`
- `memory_high_affect_max_items`
- `memory_high_affect_max_chars`
- `memory_high_affect_llm_fallback`
- `memory_nuance_enabled`
- `memory_nuance_min_score`
- `memory_nuance_callback_probability`
- `memory_nuance_cues_max_chars`
- `memory_pair_limit`
- `memory_evidence_tail_max`
- `memory_semantic_enabled`
- `memory_search_k`
- `memory_search_max_chars`
- `memory_search_time_window_rounds`
- `memory_total_max_chars`
- `memory_tier_a_max_chars`
- `memory_tier_b_max_chars`
- `memory_tier_c_max_chars`
- `memory_tier_c_uncertainty_threshold`
- `memory_digest_update_cadence_rounds`
- `memory_digest_events_limit`
- `memory_reflection_cadence_rounds`
- `memory_reflection_min_events`
- `memory_reflection_trigger_importance_sum`
- `memory_reflection_max_items_per_run`
- `memory_embedding_model`
- `memory_embedding_async`
- `memory_importance_mode`

## Backend Notes

- Text generation can run through Ollama or vLLM, following the existing
  YSimulator LLM configuration.
- Memory embeddings are configured on the client side through
  `memory_embedding_model`.
- The server actor never calls embedding or generation services directly.

## Operational Notes

- Memory is enabled only for LLM agents.
- Rule-based agents continue to behave as before.
- Prompt augmentation is applied in the action generators and LLM services
  without changing the public server APIs.

## Validation

Memory integration should be validated with:

1. unit tests for prompt/context injection and post-submit event recording
2. standard YSimulator regression tests for action generation and server paths
3. a short live run with Ollama text generation and the configured embedding model
