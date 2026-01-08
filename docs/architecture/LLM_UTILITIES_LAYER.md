# LLM Utilities Layer Architecture

**Created**: January 8, 2026  
**Phase**: 3 (Client Refactoring)  
**Status**: ✅ Production Ready

## Overview

The LLM Utilities Layer is a comprehensive framework for managing all LLM (Large Language Model) interactions in YSimulator. It provides a unified interface, automatic retry logic, response validation, and usage tracking for all LLM operations.

**Key Benefits**:
- **Unified Interface**: Single entry point for all LLM calls via LLMManager
- **Robustness**: Automatic retry with exponential backoff
- **Validation**: Response parsing and sanitization
- **Monitoring**: Comprehensive usage tracking and cost estimation
- **Future-Proof**: Ready for caching, fallback strategies, A/B testing

---

## Architecture

### Package Structure

```
YClient/llm_utils/
├── __init__.py             # Module exports
├── llm_manager.py          # Unified LLM interface (289 lines)
├── batch_handler.py        # Scatter/gather pattern (185 lines)
├── retry_handler.py        # Exponential backoff (162 lines)
├── response_parser.py      # Response validation (263 lines)
└── cost_tracker.py         # Usage tracking (179 lines)
```

**Total**: 1,088 lines of LLM utilities infrastructure

---

## Component Details

### 1. LLMManager

**Purpose**: Provides a unified, consistent interface for all LLM operations.

**Key Features**:
- Wraps the Ray LLM actor handle
- Implements all 11 LLM methods
- Consistent logging for all operations
- Single point of control for LLM calls

**Methods** (11 total):
```python
class LLMManager:
    def generate_post(...) -> Any
    def generate_news_post(...) -> Any
    def generate_image_post(...) -> Any
    def generate_comment(...) -> Any
    def generate_share_comment(...) -> Any
    def decide_follow(...) -> Any
    def extract_topics_from_article(...) -> Any
    def infer_emotion(...) -> Any
    def infer_article_opinion(...) -> Any
    def generate_secondary_follow_decision(...) -> Any
    def evaluate_opinion(...) -> Any
```

**Usage Example**:
```python
# Initialize during client setup
self.llm_manager = LLMManager(llm_handle, logger=self.logger)

# Use for all LLM calls
future = self.llm_manager.generate_post(...)
```

**Integration Points**:
- `client.py`: Initialized at line 146-156
- `action_executor.py`: Comment generation, topic extraction
- `opinion_dynamics/llm_evaluation.py`: Opinion evaluation

---

### 2. BatchHandler

**Purpose**: Implements the scatter/gather pattern for parallel LLM call processing.

**Key Features**:
- Parallel future resolution
- Error handling for Ray operations
- Metadata preservation
- Timeout support

**Methods**:
```python
class BatchHandler:
    def gather_futures(futures: List) -> List
    def gather_with_metadata(futures_with_metadata: List) -> List
    def batch_process(items: List, process_fn, rate_limit=None) -> List
    def gather_with_timeout(futures: List, timeout: float) -> List
```

**Usage Example**:
```python
# Scatter: Fire off all LLM calls
futures = [llm_manager.generate_post(...) for _ in agents]

# Gather: Wait for all results with retry
results = retry_handler.retry_with_backoff(
    batch_handler.gather_futures,
    futures
)
```

**Integration Points**:
- `simulation/batch_processor.py`: All 3 gather methods (posts, reactions, follows)

---

### 3. RetryHandler

**Purpose**: Provides automatic retry logic with exponential backoff for transient failures.

**Key Features**:
- Configurable retry attempts (default: 3)
- Exponential backoff (1s → 2s → 4s)
- Retryable error detection
- Comprehensive logging

**Configuration**:
```python
class RetryHandler:
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 60.0,
        logger: Optional[logging.Logger] = None
    )
```

**Usage Example**:
```python
# Wrap any operation with retry logic
results = retry_handler.retry_with_backoff(
    operation_func,
    *args,
    error_message="Operation description"
)
```

**Integration Points**:
- `simulation/batch_processor.py`: Wraps all gather_futures() calls

---

### 4. ResponseParser

**Purpose**: Validates and sanitizes LLM responses to ensure data quality.

**Key Features**:
- Type checking (text, boolean, list, dict)
- Default value handling
- Text sanitization (HTML removal, whitespace cleanup)
- Truncation support
- GoEmotions taxonomy validation

**Methods**:
```python
class ResponseParser:
    def parse_text_response(response, default="", max_length=None) -> str
    def parse_boolean_response(response, default=False) -> bool
    def parse_list_response(response, default=None) -> List
    def parse_dict_response(response, default=None) -> Dict
    def parse_emotion_response(response, default="neutral") -> str
    def sanitize_text(text, max_length=None) -> str
```

**Usage Example**:
```python
# Validate and sanitize LLM response
text = response_parser.parse_text_response(
    llm_result,
    default="",
    max_length=500
)
```

**Integration Points**:
- `simulation/batch_processor.py`: Validates all text responses

---

### 5. CostTracker

**Purpose**: Monitors LLM usage and tracks estimated costs.

**Key Features**:
- Dedicated log file per client
- JSON-formatted entries
- Token usage estimation
- Cumulative statistics
- Rotating logs (10MB, 5 backups)
- Optional and configurable

**Log Format**:
```json
{
  "timestamp": "2026-01-08T10:45:00.123Z",
  "method": "generate_post",
  "input_tokens": 150,
  "output_tokens": 50,
  "total_tokens": 200,
  "cumulative_calls": 42,
  "cumulative_tokens": 8400
}
```

**Configuration**:
```json
// simulation_config.json
{
  "logging": {
    "enable_llm_usage_log": true  // default: true
  }
}
```

**Usage Example**:
```python
# Track LLM call
cost_tracker.record_call(
    method="generate_post",
    input_tokens=100,
    output_tokens=50
)
```

**Integration Points**:
- `client.py`: Initialized in `_setup_cost_tracker()` (lines 505-527)
- `simulation/batch_processor.py`: Tracks all gather operations

---

## Integration Flow

### Complete LLM Call Pipeline

```
1. LLM Call Initiation
   ↓
2. LLMManager (unified interface)
   ↓ Returns Ray future
3. BatchHandler.gather_futures() (scatter/gather)
   ↓ Wrapped by
4. RetryHandler.retry_with_backoff() (automatic retry)
   ↓ Returns results
5. ResponseParser.parse_text_response() (validation)
   ↓ Clean result
6. CostTracker.record_call() (usage logging)
   ↓
7. Final Result
```

### Example Integration (BatchProcessor)

```python
class BatchProcessor:
    def __init__(self, llm, logger, cost_tracker):
        # Initialize all llm_utils components
        self.llm_manager = LLMManager(llm, logger=logger)
        self.batch_handler = BatchHandler(logger=logger)
        self.retry_handler = RetryHandler(max_retries=3, logger=logger)
        self.response_parser = ResponseParser(logger=logger)
        self.cost_tracker = cost_tracker
    
    def gather_pending_llm_posts(self, pending_llm_posts):
        # Scatter: Collect futures (already fired)
        futures = [post[2] for post in pending_llm_posts]
        
        # Gather: With retry logic
        results = self.retry_handler.retry_with_backoff(
            self.batch_handler.gather_futures,
            futures,
            error_message="Gathering LLM post futures"
        )
        
        # Process results
        actions = []
        for (agent_id, post_type, _), result in zip(pending_llm_posts, results):
            # Validate response
            text = self.response_parser.parse_text_response(result, default="")
            
            # Track usage
            input_tokens = PROMPT_TOKENS_POST
            output_tokens = len(text) // CHARS_PER_TOKEN
            self.cost_tracker.record_call("generate_post", input_tokens, output_tokens)
            
            # Create action
            if text:
                actions.append(ActionDTO(...))
        
        return actions
```

---

## Configuration

### Enable LLM Usage Logging

**File**: `simulation_config.json`

```json
{
  "logging": {
    "enable_llm_usage_log": true,  // Enable/disable LLM usage tracking
    "enable_action_log": true,
    "enable_opinion_log": true,
    "enable_recsys_log": true
  }
}
```

**Log Location**: `{experiment_dir}/log/{client_id}_llm_usage.log`

---

## Benefits

### 1. Unified Interface
- Single entry point for all LLM operations
- Consistent API across all methods
- Easy to mock for testing

### 2. Robustness
- Automatic retry for transient failures
- Exponential backoff prevents overwhelming services
- Graceful degradation with defaults

### 3. Monitoring
- Comprehensive usage tracking
- Token consumption visibility
- Cost estimation per method
- JSON format for easy analysis

### 4. Validation
- Type checking for all responses
- Sanitization and truncation
- Default value handling
- Prevents invalid data propagation

### 5. Future-Proof
- Ready for caching strategies
- Easy to add fallback LLM providers
- Simple to implement A/B testing
- Supports circuit breaker patterns

---

## Testing

### Unit Tests

**File**: `tests/test_llm_service.py` (32 tests)

**Coverage**:
- LLMManager: 4 tests (initialization, availability, method wrapping)
- BatchHandler: 5 tests (gather, metadata, errors)
- RetryHandler: 4 tests (backoff, retryable errors, max retries)
- ResponseParser: 13 tests (text, bool, list, dict, emotion, sanitization)
- CostTracker: 6 tests (recording, counting, costs, summary, reset)

**All Tests Passing**: ✅ 32/32

---

## Performance Considerations

### Token Estimation

**Constants** (defined in `batch_processor.py`):
```python
CHARS_PER_TOKEN = 4          # ~4 characters per token
PROMPT_TOKENS_POST = 100     # Estimated prompt for post
PROMPT_TOKENS_COMMENT = 120  # Estimated prompt for comment
PROMPT_TOKENS_FOLLOW = 60    # Estimated prompt for follow
REACTION_OUTPUT_TOKENS = 5   # Simple reaction outputs
```

### Retry Configuration

**Defaults**:
- Max retries: 3
- Initial delay: 1.0s
- Backoff factor: 2.0
- Max delay: 60.0s

**Retry Sequence**: 1s → 2s → 4s → fail

---

## Future Enhancements

### Potential Additions

1. **Caching Layer**
   - Cache LLM responses for identical inputs
   - Reduce API costs and latency
   - Configurable TTL

2. **Fallback Strategies**
   - Multiple LLM providers
   - Automatic failover
   - Provider selection based on cost/latency

3. **A/B Testing**
   - Compare different prompts
   - Measure quality metrics
   - Automated optimization

4. **Circuit Breaker**
   - Detect sustained failures
   - Temporary disable LLM calls
   - Graceful degradation to rule-based

5. **Rate Limiting**
   - Token-per-second limits
   - Request batching
   - Queue management

6. **Advanced Monitoring**
   - Latency tracking
   - Success rate metrics
   - Cost per simulation
   - Dashboard integration

---

## Related Documentation

- [CLIENT_REFACTORING_REPORT.md](../refactoring/CLIENT_REFACTORING_REPORT.md) - Complete refactoring history
- [SIMULATION_ORCHESTRATOR.md](SIMULATION_ORCHESTRATOR.md) - Phase 2 architecture
- [ARCHITECTURE.md](ARCHITECTURE.md) - Overall system architecture
- [ACTION_GENERATOR_FRAMEWORK.md](../refactoring/ACTION_GENERATOR_FRAMEWORK.md) - Phase 1 details

---

## Summary

The LLM Utilities Layer provides a robust, maintainable, and future-proof foundation for all LLM interactions in YSimulator. With 100% coverage of LLM methods, automatic retry logic, comprehensive validation, and detailed usage tracking, it ensures reliable and observable LLM operations while maintaining clean separation of concerns and excellent testability.

**Status**: ✅ **Production Ready** - All 5 modules fully integrated and operational
