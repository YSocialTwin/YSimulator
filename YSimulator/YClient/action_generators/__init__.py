"""
Action generator framework for YSimulator agents.

This package provides a pluggable action generation system that separates
action generation logic from the main simulation client. Each action type
(POST, COMMENT, READ, etc.) has its own generator class that handles both
LLM and rule-based agent behaviors.

The framework follows the Strategy pattern to enable:
- Single responsibility per generator
- Easy testing in isolation
- Clear separation of LLM vs rule-based logic
- Simple addition of new action types
- Reusability across contexts

Usage:
    from YSimulator.YClient.action_generators import ActionGeneratorFactory
    
    factory = ActionGeneratorFactory(server, llm, news_service, logger, ...)
    generator = factory.get_generator("POST", "llm")
    result = generator.generate(agent, context)
"""

from YSimulator.YClient.action_generators.base_generator import (
    ActionContext,
    ActionGeneratorResult,
    BaseActionGenerator,
)
from YSimulator.YClient.action_generators.factory import ActionGeneratorFactory

__all__ = [
    "BaseActionGenerator",
    "ActionContext",
    "ActionGeneratorResult",
    "ActionGeneratorFactory",
]
