"""
Base classes for action processing framework.

Defines abstract base class and data structures for action processing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging


@dataclass
class ActionContext:
    """
    Context information for action processing.

    Provides shared state and configuration needed by action processors.
    """

    current_round_id: str
    day: int
    slot: int
    # Add additional context fields as needed


@dataclass
class ActionResult:
    """
    Result of action processing.

    Contains status, generated IDs, and metadata about the processed action.
    """

    success: bool
    action_type: str
    agent_id: str
    new_ids: List[str] = field(default_factory=list)  # Post IDs, etc.
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseActionProcessor(ABC):
    """
    Abstract base class for action processors.

    Each action type (POST, COMMENT, FOLLOW, etc.) has a dedicated processor
    that implements this interface.
    """

    def __init__(self, services: Any, logger: Optional[logging.Logger] = None):
        """
        Initialize action processor.

        Args:
            services: Service container or database adapter providing data access
            logger: Logger instance for recording processing events
        """
        self.services = services
        self.logger = logger or logging.getLogger(__name__)

    @abstractmethod
    def process(self, action: Any, context: ActionContext) -> ActionResult:
        """
        Process an action.

        Args:
            action: ActionDTO object containing action details
            context: ActionContext with simulation state information

        Returns:
            ActionResult with processing outcome
        """

    def validate(self, action: Any) -> bool:
        """
        Validate action before processing.

        Args:
            action: ActionDTO object to validate

        Returns:
            True if valid, False otherwise

        Note: Default implementation returns True. Override if validation needed.
        """
        return True
