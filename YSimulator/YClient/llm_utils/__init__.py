"""
LLM Utilities Module for YClient.

This module provides centralized LLM interaction management, including:
- LLM request coordination
- Batch processing with scatter/gather pattern
- Error handling and retry logic
- Response validation
- Cost tracking (optional)

Extracted as part of Phase 3 refactoring to improve:
- Testability (easy to mock LLM calls)
- Error handling (centralized retry logic)
- Maintainability (single place for LLM interactions)
- Monitoring (cost and usage tracking)

Renamed from llm_service to llm_utils to avoid confusion with
LLM_interactions/llm_service.py (the actual LLM implementation).
"""

# Import components that don't require Ray
from YSimulator.YClient.llm_utils.cost_tracker import CostTracker
from YSimulator.YClient.llm_utils.response_parser import ResponseParser

# Import Ray-dependent components (may fail if Ray not installed)
try:
    from YSimulator.YClient.llm_utils.batch_handler import BatchHandler
    from YSimulator.YClient.llm_utils.llm_manager import LLMManager
    from YSimulator.YClient.llm_utils.load_balancer import (
        LLMActorPool,
        LLMLoadBalancer,
        LoadBalancingStrategy,
        acquire_llm_pool_lease,
        create_llm_actors,
        release_llm_pool_lease,
    )
    from YSimulator.YClient.llm_utils.retry_handler import RetryHandler
except ImportError:
    # Ray not available - these components won't work but others will
    BatchHandler = None
    LLMManager = None
    RetryHandler = None
    LLMLoadBalancer = None
    LLMActorPool = None
    LoadBalancingStrategy = None
    acquire_llm_pool_lease = None
    create_llm_actors = None
    release_llm_pool_lease = None

__all__ = [
    "LLMManager",
    "BatchHandler",
    "RetryHandler",
    "ResponseParser",
    "CostTracker",
    "LLMLoadBalancer",
    "LLMActorPool",
    "LoadBalancingStrategy",
    "acquire_llm_pool_lease",
    "create_llm_actors",
    "release_llm_pool_lease",
]
