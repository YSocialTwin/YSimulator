"""
Agent Management Module for YClient.

This module provides centralized agent lifecycle management including:
- Agent creation and registration
- Social network loading and management
- Agent selection and activity coordination
- Agent profile updates and persistence

Phase 6 of CLIENT_REFACTORING_REPORT.md - Extracted from client.py for better
separation of concerns and testability.
"""

from YSimulator.YClient.agent_management.agent_manager import AgentManager
from YSimulator.YClient.agent_management.agent_selector import AgentSelector
from YSimulator.YClient.agent_management.network_loader import NetworkLoader
from YSimulator.YClient.agent_management.population_loader import PopulationLoader

__all__ = [
    "AgentManager",
    "PopulationLoader",
    "NetworkLoader",
    "AgentSelector",
]
