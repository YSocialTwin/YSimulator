"""
Simulation Orchestration Module for YClient.

This module contains components for simulation orchestration extracted from client.py
as part of Phase 2 refactoring. It separates simulation control flow from agent logic.

Components:
- simulator: Main simulation coordinator
- round_executor: Per-round execution logic
- agent_scheduler: Agent selection and scheduling
- batch_processor: LLM batch processing (scatter/gather pattern)
- lifecycle_manager: Agent lifecycle (churn, follows, new agents)
- follow_decay_manager: Time-based follow action probability decay
"""

from YSimulator.YClient.simulation.agent_scheduler import AgentScheduler
from YSimulator.YClient.simulation.batch_processor import BatchProcessor
from YSimulator.YClient.simulation.follow_decay_manager import FollowDecayManager
from YSimulator.YClient.simulation.lifecycle_manager import LifecycleManager
from YSimulator.YClient.simulation.round_executor import RoundExecutor
from YSimulator.YClient.simulation.simulator import Simulator

__all__ = [
    "Simulator",
    "RoundExecutor",
    "AgentScheduler",
    "BatchProcessor",
    "LifecycleManager",
    "FollowDecayManager",
]
