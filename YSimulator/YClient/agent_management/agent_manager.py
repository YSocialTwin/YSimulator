"""
Agent Manager - Main Coordinator for Agent Management.

Provides unified interface for all agent lifecycle operations.
Phase 6 of CLIENT_REFACTORING_REPORT.md.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from YSimulator.YClient.agent_management.agent_selector import AgentSelector
from YSimulator.YClient.agent_management.network_loader import NetworkLoader
from YSimulator.YClient.agent_management.population_loader import PopulationLoader
from YSimulator.YClient.classes.ray_models import AgentProfile


class AgentManager:
    """
    Unified interface for agent lifecycle management.
    
    Coordinates:
    - PopulationLoader: Agent creation and persistence
    - NetworkLoader: Social network topology
    - AgentSelector: Agent selection and type determination
    
    This class integrates the three specialized components and provides
    a clean API for client.py to interact with agent management operations.
    """
    
    def __init__(
        self,
        config_path: Path,
        server,
        client_id: str,
        archetype_distribution: Dict[str, float],
        agent_downcast: bool,
        actions_likelihood: Dict,
        logger: logging.Logger
    ):
        """
        Initialize AgentManager.
        
        Args:
            config_path: Path to configuration directory
            server: Ray server actor handle
            client_id: Client identifier
            archetype_distribution: Distribution weights for archetypes
            agent_downcast: Whether to downcast certain agent types
            actions_likelihood: Action probability configuration
            logger: Logger instance
        """
        self.config_path = config_path
        self.server = server
        self.client_id = client_id
        self.logger = logger
        
        # Initialize specialized components
        self.population_loader = PopulationLoader(config_path, client_id, logger)
        self.network_loader = NetworkLoader(server, client_id, logger)
        self.agent_selector = AgentSelector(
            archetype_distribution,
            agent_downcast,
            actions_likelihood,
            logger
        )
    
    # ========== Population Management ==========
    
    def create_agents_from_config(self, agent_config: dict) -> List[AgentProfile]:
        """Create agent profiles from configuration."""
        return self.population_loader.create_agents_from_config(agent_config)
    
    def save_updated_agent_population(self, updated_interests: Dict):
        """Save updated agent interests to configuration file."""
        self.population_loader.save_updated_agent_population(updated_interests)
    
    def add_agent_to_population_file(self, agent: AgentProfile):
        """Add a new agent to the configuration file."""
        self.population_loader.add_agent_to_population_file(agent)
    
    def validate_and_extract_interests(self, interests):
        """Validate interests structure and extract topics and counts."""
        return self.population_loader.validate_and_extract_interests(interests)
    
    # ========== Network Management ==========
    
    def parse_network_edges(self, network_csv_path: Path, agent_profiles: List[AgentProfile]) -> List:
        """Parse network edges from CSV file."""
        return self.network_loader.parse_network_edges(network_csv_path, agent_profiles)
    
    def load_and_create_social_network(self, network_csv_path: Path, agent_profiles: List[AgentProfile]) -> int:
        """Load network edges and create follow relationships."""
        return self.network_loader.load_and_create_social_network(network_csv_path, agent_profiles)
    
    # ========== Agent Selection ==========
    
    def sample_agents_by_archetype(self, available_agents: List[AgentProfile], num_active: int) -> List[AgentProfile]:
        """Sample agents according to archetype distribution."""
        return self.agent_selector.sample_agents_by_archetype(available_agents, num_active)
    
    def determine_agent_type(self, agent_profile: AgentProfile) -> str:
        """Determine agent type (llm or rule_based)."""
        return self.agent_selector.determine_agent_type(agent_profile)
    
    def select_action(self, agent_profile: AgentProfile, recent_posts: list):
        """Determine which action an agent should perform."""
        return self.agent_selector.select_action(agent_profile, recent_posts)
    
    def extract_agent_attrs(
        self,
        agent: AgentProfile,
        validate_and_extract_interests_func,
        is_opinion_dynamics_enabled_func,
        map_opinion_to_group_func
    ) -> dict:
        """Extract agent attributes for persona building."""
        return self.agent_selector.extract_agent_attrs(
            agent,
            validate_and_extract_interests_func,
            is_opinion_dynamics_enabled_func,
            map_opinion_to_group_func
        )
