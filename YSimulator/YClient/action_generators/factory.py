"""
Factory for creating action generators.

This module provides a centralized factory for instantiating the appropriate
action generator based on action type. The factory pattern enables:
- Clean separation of generator instantiation logic
- Easy addition of new action types
- Consistent configuration across all generators
"""

from typing import Dict, Type

from YSimulator.YClient.action_generators.base_generator import (
    ActionContext,
    BaseActionGenerator,
)


class ActionGeneratorFactory:
    """
    Factory for creating action generators.
    
    This factory maintains a registry of action type -> generator class mappings
    and instantiates generators with the appropriate context.
    
    Usage:
        context = ActionContext(day=1, slot=5, ...)
        factory = ActionGeneratorFactory(context)
        generator = factory.get_generator("POST")
        result = generator.generate(agent, "llm")
    """
    
    def __init__(self, context: ActionContext):
        """
        Initialize the factory with action context.
        
        Args:
            context: Action context to pass to all generators
        """
        self.context = context
        self._registry: Dict[str, Type[BaseActionGenerator]] = {}
        self._register_default_generators()
    
    def _register_default_generators(self):
        """Register all built-in action generators."""
        # Import generators here to avoid circular dependencies
        from YSimulator.YClient.action_generators.cast_generator import CastGenerator
        from YSimulator.YClient.action_generators.comment_generator import CommentGenerator
        from YSimulator.YClient.action_generators.follow_generator import FollowGenerator
        from YSimulator.YClient.action_generators.image_generator import ImageGenerator
        from YSimulator.YClient.action_generators.post_generator import PostGenerator
        from YSimulator.YClient.action_generators.read_generator import ReadGenerator
        from YSimulator.YClient.action_generators.search_generator import SearchGenerator
        from YSimulator.YClient.action_generators.share_generator import ShareGenerator
        from YSimulator.YClient.action_generators.share_link_generator import (
            ShareLinkGenerator,
        )
        
        # Register generators by action type
        self._registry["post"] = PostGenerator
        self._registry["comment"] = CommentGenerator
        self._registry["read"] = ReadGenerator
        self._registry["follow"] = FollowGenerator
        self._registry["share_link"] = ShareLinkGenerator
        self._registry["share"] = ShareGenerator
        self._registry["search"] = SearchGenerator
        self._registry["image"] = ImageGenerator
        self._registry["cast"] = CastGenerator
    
    def register_generator(self, action_type: str, generator_class: Type[BaseActionGenerator]):
        """
        Register a custom action generator.
        
        This allows extending the framework with new action types without
        modifying the factory code.
        
        Args:
            action_type: Action type identifier (e.g., "custom_action")
            generator_class: Generator class to instantiate for this action type
        """
        self._registry[action_type.lower()] = generator_class
    
    def get_generator(self, action_type: str) -> BaseActionGenerator:
        """
        Get an action generator for the specified action type.
        
        Args:
            action_type: Action type (e.g., "POST", "COMMENT", "READ")
        
        Returns:
            BaseActionGenerator: Instance of the appropriate generator
        
        Raises:
            ValueError: If action_type is not registered
        """
        action_type_lower = action_type.lower()
        
        if action_type_lower not in self._registry:
            raise ValueError(
                f"Unknown action type: {action_type}. "
                f"Registered types: {list(self._registry.keys())}"
            )
        
        generator_class = self._registry[action_type_lower]
        return generator_class(self.context)
    
    def has_generator(self, action_type: str) -> bool:
        """
        Check if a generator is registered for the action type.
        
        Args:
            action_type: Action type to check
        
        Returns:
            bool: True if generator is registered
        """
        return action_type.lower() in self._registry
    
    def list_action_types(self) -> list:
        """
        List all registered action types.
        
        Returns:
            list: Sorted list of registered action types
        """
        return sorted(self._registry.keys())
