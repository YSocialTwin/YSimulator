# Memory Module Integration – Regression Report

## Executive Summary

An audit of the memory module integration changes (commit `3c5b9ed` – *refactor(memory): inherit ghostkg llm config from top-level llm*) revealed **63 test failures across 8 test files** out of a total suite of 978 tests (915 pass, 33 skipped).

The failures fall into two distinct categories:

| Category | Files affected | # Failures | Nature |
|---|---|---|---|
| **API-contract breaks** | 6 files | 32 | Deterministic – fail in isolation |
| **Test-isolation failures** | 2 files | 27+4 | Non-deterministic – pass alone, fail in full suite |

All memory-module-specific tests (29 tests spanning `test_memory_settings`, `test_memory_backend_factory`, `test_ghostkg_backend_adapter`, `test_native_memory_backend`, `test_client_memory_runtime`, `test_memory_service_health`, `test_memory_prompt_budget`) **pass cleanly**.

---

## Part 1 – Broken Patterns (API-contract breaks)

### P-1 · `generate_news_post_async` return-value arity

**Affected tests**: `test_llm_actions_comprehensive.py::TestGenerateNewsPostAsync` (3 tests)

**What changed**: `YSimulator/YClient/actions/llm_actions.py` – the function now returns a 3-tuple `(commentary_future, article_id, article)` to avoid a follow-up DB fetch. The previous contract was a 2-tuple `(commentary_future, article_id)`.

```python
# OLD – caller expected
commentary_future, article_id = generate_news_post_async(...)

# NEW – function now returns
return commentary_future, article_id, article   # ← extra element breaks unpack
```

**Impact**: Every call site that unpacks exactly two values (`commentary_future, article_id = ...`) raises `ValueError: too many values to unpack`.

---

### P-2 · `generate_image_post_async` signature overhaul

**Affected tests**: `test_llm_actions_comprehensive.py::TestGenerateImagePostAsync` (5 tests)

**What changed**: The function signature was replaced with a different parameter set used by the new image generator architecture. Tests use the old keyword arguments (`agent_cluster`, `image_data`, `topics`) that no longer exist in the current signature `(llm_handle, cluster_id, day, slot, agent_attrs, agent_id)`.

```python
# OLD signature expected by tests
generate_image_post_async(server, llm_service, agent_cluster=1, image_data={...})

# NEW signature in source
generate_image_post_async(llm_handle, cluster_id, day, slot, agent_attrs, agent_id)
```

---

### P-3 · ReCSys functions return `(list, bool)` tuple instead of `list`

**Affected tests**: `test_content_recsys_db.py` (11 tests)

**What changed**: The following server-side recommendation functions in `YSimulator/YServer/recsys/content_recsys_db.py` now return a 2-tuple `(post_ids: list, from_cache: bool)`:

- `recommend_common_interests`
- `recommend_common_user_interests`
- `recommend_similar_users_react`
- `recommend_similar_users_posts`
- `hybrid_linear_ranker` (related signature issue)

**Impact**: Tests that assert `len(result) == 5` receive `len(result) == 2` because `result` is a tuple of two elements (the list plus the bool flag).

```python
# Expected by tests
result = recommend_common_interests(...)
assert len(result) == 5          # fails: len(result) == 2 (it's a 2-tuple)
assert result == ['post1', ...]  # fails: result is (['post1', ...], False)
```

---

### P-4 · `content_recsys_redis` removed module-level `Session` attribute

**Affected tests**: `test_hybrid_recsys_redis.py` (5 tests)

**What changed**: Tests patch `YSimulator.YServer.recsys.content_recsys_redis.Session` via `monkeypatch.setattr(module, 'Session', ...)`. After the refactoring, `Session` is no longer imported at module level in `content_recsys_redis.py`.

```python
# Tests attempt (fails)
monkeypatch.setattr(content_recsys_redis, 'Session', MockSession)
# AttributeError: module … does not have the attribute 'Session'
```

---

### P-5 · `ContentRecSys.RandomOrder.mode` value changed

**Affected tests**: `test_recommender_systems_comprehensive.py::TestContentRecSysClient::test_random_order` (1 test)

**What changed**: `RandomOrder.__init__` in `YSimulator/YClient/recsys/ContentRecSys.py` now calls `super().__init__(mode="random", ...)` instead of using the parent class default `"ContentRecSys"`. Tests assert `recsys.mode == "ContentRecSys"`.

```python
# Test asserts
assert recsys.mode == "ContentRecSys"   # fails: actual value is "random"
```

---

### P-6 · `gpu_utils.torch` no longer a module-level attribute

**Affected tests**: `test_gpu_utils.py` (5 tests)

**What changed**: `YSimulator/YClient/llm_utils/gpu_utils.py` moved the `import torch` statement inside individual functions (lazy import). Tests patch `torch` at module level via `@patch('YSimulator.YClient.llm_utils.gpu_utils.torch', ...)`.

```python
# Tests attempt
@patch('YSimulator.YClient.llm_utils.gpu_utils.torch', mock_torch)
# AttributeError: module … does not have the attribute 'torch'
```

---

### P-7 · `vllm_service.py` CUDA/PyTorch error message strings removed

**Affected tests**: `test_vllm_error_handling.py::test_cuda_not_available_error_message` (1 test)

**What changed**: Specific human-readable strings that act as a contract for operator visibility (`"CUDA is not available but is required"`, `"PyTorch is not installed"`, `"PyTorch is required"`) were removed from `YSimulator/YClient/LLM_interactions/vllm_service.py` during the refactoring.

```python
# Test asserts presence of string
self.assertIn("CUDA is not available but is required", source_code)  # fails
```

---

## Part 2 – Test-isolation Failures

### I-1 · `test_server.py` and `test_opinion_manager.py` – global state pollution

**Affected tests**: `test_server.py` (23 tests), `test_opinion_manager.py` (4 tests) – only fail in the full test suite; pass when executed in isolation.

**Root cause**: Earlier test files modify shared global/singleton state (likely Ray actor handles, module-level singletons, or `sys.modules` entries injected by `monkeypatch`) that is not fully reset between test modules. When the full suite runs in alphabetical order these modules inherit dirty state.

**Indicators**:
- All tests in both files pass when run with `pytest YSimulator/tests/test_server.py`.
- Both files fail with state-corruption errors (wrong mock return values, missing attributes) when preceded by `test_hybrid_recsys_redis.py` or `test_gpu_utils.py`.

---

## Part 3 – Fix Pipeline

### Sprint 1 – High-priority API-contract fixes (P-1 through P-5)

#### Step 1.1 – Fix `generate_news_post_async` callers (P-1)

- **Option A (preferred – minimal diff)**: Restore 2-tuple return and pass `article` via a separate dedicated channel (e.g., add it to a `metadata` dict already present downstream).
- **Option B**: Update every call site to unpack 3 values and update the 3 affected tests to match the 3-tuple.
- **Test gate**: `test_llm_actions_comprehensive.py::TestGenerateNewsPostAsync` – all 3 tests pass.

#### Step 1.2 – Fix `generate_image_post_async` signature or tests (P-2)

- **Option A (preferred)**: The old signature was a well-defined contract; restore it or add a compatibility shim.
- **Option B**: Rewrite the 5 tests to match the new signature and document the migration.
- **Test gate**: `test_llm_actions_comprehensive.py::TestGenerateImagePostAsync` – all 5 tests pass.

#### Step 1.3 – Fix ReCSys return type (P-3)

- **Option A (preferred)**: Restore single-list return from `recommend_*` functions and propagate the `from_cache` flag via an out-of-band mechanism (e.g., logging or a separate cache-stats endpoint).
- **Option B**: Update all 11 affected tests and all upstream callers to handle the tuple.
- **Test gate**: `test_content_recsys_db.py` – all 34 tests pass (11 currently failing).

#### Step 1.4 – Restore `Session` import in `content_recsys_redis` (P-4)

- Add `from sqlalchemy.orm import Session` back at the top of `content_recsys_redis.py`.
- **Test gate**: `test_hybrid_recsys_redis.py` – all 6 currently failing tests pass.

#### Step 1.5 – Clarify `RandomOrder.mode` value (P-5)

Two valid resolutions exist; the choice depends on intent:

- **Option A (backward-compatible – preferred if mode is used as an identifier)**: Revert `super().__init__(mode="ContentRecSys", ...)` in `ContentRecSys.RandomOrder`, making the mode the parent-class default. Update code comments to clarify that `RandomOrder` is a strategy variant of `ContentRecSys`.
- **Option B (if `"random"` is the correct semantic value)**: Keep `mode="random"` and update the single test assertion to match. Add a decision note to `ContentRecSys.py` explaining that `RandomOrder` has its own distinct mode identifier.

Regardless of which option is chosen, the resolution must be captured in a code comment so future contributors understand the intent.

- **Test gate**: `test_recommender_systems_comprehensive.py::TestContentRecSysClient::test_random_order` passes.

---

### Sprint 2 – Module-level attribute fixes (P-6, P-7)

#### Step 2.1 – Expose `torch` at module level in `gpu_utils` (P-6)

- Move `import torch` to the top of `gpu_utils.py` inside a `try/except ImportError` block so that `monkeypatch` can target the module attribute.
- **Test gate**: `test_gpu_utils.py` – all 5 currently failing tests pass.

#### Step 2.2 – Restore CUDA/PyTorch error messages (P-7)

- Re-add the following strings to the `_initialize` method of `VLLMService`:
  - `"CUDA is not available but is required"`
  - `"PyTorch is not installed"`
  - `"PyTorch is required"`
- **Test gate**: `test_vllm_error_handling.py` – all 5 tests pass (currently 1 fails, 4 pass).

---

### Sprint 3 – Test isolation fixes (I-1)

#### Step 3.1 – Identify state-polluting modules

- Run the suite with `pytest --randomly-seed=last` to confirm order-dependency.
- Use `pytest-isolate` or `--forked` to narrow down the source test file that corrupts state.

#### Step 3.2 – Add teardown guards

- Ensure any test that calls `monkeypatch.setitem(sys.modules, ...)` is wrapped in a proper `monkeypatch` fixture (not raw `sys.modules` manipulation) so state is rolled back automatically after each test.
- Add a session-scoped `autouse` fixture that resets Ray remote-actor references between test modules.

#### Step 3.3 – Verify

- **Test gate**: Running the full suite in any order produces the same results as running each file individually.

---

## Part 4 – Success Criteria

The following table defines measurable, binary success criteria that can be evaluated by re-running the test suite after each sprint.

| ID | Criterion | Measurement | Target |
|---|---|---|---|
| SC-1 | All memory module tests still pass | `pytest YSimulator/tests/ -k "memory or ghostkg"` | 29/29 pass |
| SC-2 | `generate_news_post_async` API contract restored | `pytest test_llm_actions_comprehensive.py::TestGenerateNewsPostAsync` | 3/3 pass |
| SC-3 | `generate_image_post_async` API contract restored | `pytest test_llm_actions_comprehensive.py::TestGenerateImagePostAsync` | 5/5 pass |
| SC-4 | ReCSys functions return list (not tuple) | `pytest test_content_recsys_db.py` | 34/34 pass |
| SC-5 | Redis ReCSys `Session` attribute available | `pytest test_hybrid_recsys_redis.py` | All pass |
| SC-6 | `RandomOrder.mode` value is correct | `pytest test_recommender_systems_comprehensive.py::TestContentRecSysClient::test_random_order` | Passes; decision log updated to record whether `"random"` or `"ContentRecSys"` is the canonical value |
| SC-7 | `gpu_utils.torch` patchable at module level | `pytest test_gpu_utils.py` | 5/5 pass |
| SC-8 | CUDA/PyTorch error messages present in `vllm_service.py` | `pytest test_vllm_error_handling.py` | 5/5 pass |
| SC-9 | No test-order-dependent failures | `pytest YSimulator/tests/ --randomly-seed=12345` and `--randomly-seed=99999` | 0 failures in both runs |
| SC-10 | Full suite regression-free | `pytest YSimulator/tests/` | 0 additional failures beyond the pre-integration baseline |

---

## Part 5 – Files Requiring Changes

| File | Change required |
|---|---|
| `YSimulator/YClient/actions/llm_actions.py` | Restore 2-tuple return for `generate_news_post_async`, or update all callers |
| `YSimulator/YClient/actions/llm_actions.py` | Restore or shim `generate_image_post_async` signature |
| `YSimulator/YServer/recsys/content_recsys_db.py` | Restore single-list return for `recommend_*` functions |
| `YSimulator/YServer/recsys/content_recsys_redis.py` | Re-add `from sqlalchemy.orm import Session` at module level |
| `YSimulator/YClient/recsys/ContentRecSys.py` | Clarify intended `mode` value for `RandomOrder` |
| `YSimulator/YClient/llm_utils/gpu_utils.py` | Make `torch` import module-level (with `try/except`) |
| `YSimulator/YClient/LLM_interactions/vllm_service.py` | Restore CUDA/PyTorch operator-visible error strings |
| `YSimulator/tests/test_server.py` | Add teardown to prevent global state leak |
| `YSimulator/tests/test_opinion_manager.py` | Add teardown to prevent global state leak |
