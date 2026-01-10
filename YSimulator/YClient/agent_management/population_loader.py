"""
Population Loader for Agent Management.

Handles agent creation from configuration files and agent profile management.
"""

import json
import logging
import random
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from YSimulator.YClient.classes.ray_models import AgentProfile


class PopulationLoader:
    """
    Manages agent population loading and creation from configuration.

    Responsibilities:
    - Load predefined agents from configuration files
    - Generate additional agents based on generation_config
    - Validate and extract agent interests
    - Save updated agent populations back to configuration files
    """

    def __init__(self, config_path: Path, client_id: str, logger: logging.Logger):
        """
        Initialize PopulationLoader.

        Args:
            config_path: Path to configuration directory
            client_id: Client identifier
            logger: Logger instance
        """
        self.config_path = config_path
        self.client_id = client_id
        self.logger = logger
        self.AGENT_UUID_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")

    def create_agents_from_config(self, agent_config: dict) -> List[AgentProfile]:
        """
        Create agent profiles from configuration.
        Combines predefined agents with generated agents.

        Args:
            agent_config: Agent configuration dictionary

        Returns:
            List of AgentProfile objects
        """
        agents = []

        # Load predefined agents
        if "agents" in agent_config:
            agents.extend(self._load_predefined_agents(agent_config["agents"]))

        # Generate additional agents if specified
        if "generation_config" in agent_config:
            agents.extend(self._generate_agents(agent_config["generation_config"], len(agents)))

        self.logger.info(f"Created {len(agents)} agent profiles from configuration")
        return agents

    def _load_predefined_agents(self, agents_config: List[dict]) -> List[AgentProfile]:
        """Load predefined agents from configuration."""
        agents = []
        for agent_data in agents_config:
            profile = AgentProfile(
                id=agent_data.get("id"),
                username=agent_data.get("username"),
                email=agent_data.get("email", ""),
                password=agent_data.get("password", "simulation_agent"),
                leaning=agent_data.get("leaning", "neutral"),
                user_type=agent_data.get("user_type", "agent"),
                age=agent_data.get("age", 0),
                oe=agent_data.get("oe"),
                co=agent_data.get("co"),
                ex=agent_data.get("ex"),
                ag=agent_data.get("ag"),
                ne=agent_data.get("ne"),
                recsys_type=agent_data.get("recsys_type", "random"),
                frecsys_type=agent_data.get("frecsys_type", "default"),
                language=agent_data.get("language", "en"),
                education_level=agent_data.get("education_level"),
                joined_on=agent_data.get("joined_on"),
                gender=agent_data.get("gender"),
                nationality=agent_data.get("nationality"),
                profession=agent_data.get("profession", ""),
                activity_profile=agent_data.get("activity_profile", "Always On"),
                archetype=agent_data.get("archetype"),
                cluster=agent_data.get("cluster", 0),
                llm=agent_data.get("llm", False),
                toxicity=agent_data.get("toxicity", "no"),
                daily_activity_level=agent_data.get("daily_activity_level", 1),
                round_actions=agent_data.get("round_actions", 3),
                is_page=agent_data.get("is_page", 0),
                feed_url=agent_data.get("feed_url"),
                interests=agent_data.get("interests"),
                opinions=agent_data.get("opinions"),
            )
            agents.append(profile)
        return agents

    def _generate_agents(self, gen_config: dict, existing_count: int) -> List[AgentProfile]:
        """Generate additional agents based on generation configuration."""
        agents = []
        num_additional = gen_config.get("num_additional_agents", 0)
        cluster_weights = gen_config["cluster_distribution"]["weights"]
        llm_prob = gen_config.get("llm_enabled_probability", 0.1)
        defaults = gen_config.get("default_settings", {})
        age_range = gen_config.get("age_range", [18, 65])

        # Start indexing after predefined agents
        start_index = 10000 if existing_count > 0 else 1

        # Lists for random selection
        archetypes = ["validator", "broadcaster", "explorer"]
        activity_profiles = ["Always On", "Morning Active", "Evening Active", "Weekend Warrior"]
        professions = ["Engineer", "Teacher", "Designer", "Writer", "Analyst", "Manager"]
        genders = ["male", "female", "non-binary"]
        nationalities = ["US", "UK", "CA", "AU", "EU"]
        education_levels = ["high_school", "college", "graduate", "phd"]

        for i in range(num_additional):
            agent_index = start_index + i
            agent_id = str(uuid.uuid5(self.AGENT_UUID_NAMESPACE, f"generated_agent_{agent_index}"))
            cluster = random.choices([0, 1, 2], weights=cluster_weights)[0]

            profile = AgentProfile(
                id=agent_id,
                username=f"agent_{agent_index:04d}",
                email=f"agent{agent_index}@simulation.local",
                password=defaults.get("password", "simulation_agent"),
                leaning=defaults.get("leaning", "neutral"),
                user_type=defaults.get("user_type", "agent"),
                age=random.randint(age_range[0], age_range[1]),
                oe=random.choice(["low", "medium", "high"]),
                co=random.choice(["low", "medium", "high"]),
                ex=random.choice(["low", "medium", "high"]),
                ag=random.choice(["low", "medium", "high"]),
                ne=random.choice(["low", "medium", "high"]),
                language=defaults.get("language", "en"),
                education_level=random.choice(education_levels),
                joined_on=None,
                gender=random.choice(genders),
                nationality=random.choice(nationalities),
                profession=random.choice(professions),
                activity_profile=random.choice(activity_profiles),
                archetype=archetypes[cluster],
                cluster=cluster,
                llm=random.random() < llm_prob,
                toxicity=defaults.get("toxicity", "no"),
                daily_activity_level=random.randint(1, 4),
                round_actions=defaults.get("round_actions", 3),
                is_page=defaults.get("is_page", 0),
            )
            agents.append(profile)

        return agents

    def save_updated_agent_population(self, updated_interests: Dict[str, Dict[str, List]]):
        """
        Save updated agent interests to agent_population.json at end of day.

        Args:
            updated_interests: Dict of {agent_id: {"topics": [...], "counts": [...]}}
        """
        agent_config_file = self._get_agent_config_file()

        if not agent_config_file or not agent_config_file.exists():
            self.logger.warning("Agent config file not found, skipping interests update")
            return

        try:
            # Load current configuration
            with open(agent_config_file, "r") as f:
                agent_data = json.load(f)

            # Update interests for each agent
            if "agents" in agent_data:
                for agent in agent_data["agents"]:
                    agent_id = agent.get("id")
                    if agent_id and str(agent_id) in updated_interests:
                        interests_data = updated_interests[str(agent_id)]
                        agent["interests"] = [interests_data["topics"], interests_data["counts"]]

            # Write updated data back
            with open(agent_config_file, "w") as f:
                json.dump(agent_data, f, indent=2)

            self.logger.info(
                f"Updated {agent_config_file.name}with interests for {len(updated_interests)}agents"
            )

        except Exception as e:
            self.logger.error(
                f"Error updating agent population file: {e}",
                extra={"extra_data": {"error": str(e), "file": str(agent_config_file)}},
            )

    def add_agent_to_population_file(self, agent: AgentProfile):
        """
        Add a new agent to the agent_population.json file.

        Args:
            agent: AgentProfile to add
        """
        agent_config_file = self._get_agent_config_file()

        if not agent_config_file or not agent_config_file.exists():
            self.logger.warning("Agent config file not found, skipping agent addition")
            return

        try:
            # Load current configuration
            with open(agent_config_file, "r") as f:
                agent_data = json.load(f)

            # Create agent dict
            agent_dict = {
                "id": agent.id,
                "username": agent.username,
                "email": agent.email,
                "password": agent.password,
                "leaning": agent.leaning,
                "user_type": agent.user_type,
                "age": agent.age,
                "oe": agent.oe,
                "co": agent.co,
                "ex": agent.ex,
                "ag": agent.ag,
                "ne": agent.ne,
                "language": agent.language,
                "education_level": agent.education_level,
                "joined_on": agent.joined_on,
                "gender": agent.gender,
                "nationality": agent.nationality,
                "profession": agent.profession,
                "activity_profile": agent.activity_profile,
                "archetype": agent.archetype,
                "cluster": agent.cluster,
                "llm": agent.llm,
                "toxicity": agent.toxicity,
                "daily_activity_level": agent.daily_activity_level,
                "round_actions": agent.round_actions,
                "is_page": agent.is_page,
            }

            # Add to agents list
            if "agents" not in agent_data:
                agent_data["agents"] = []
            agent_data["agents"].append(agent_dict)

            # Write updated data back
            with open(agent_config_file, "w") as f:
                json.dump(agent_data, f, indent=2)

            self.logger.info(f"Added agent {agent.username} to {agent_config_file.name}")

        except Exception as e:
            self.logger.error(
                f"Error adding agent to population file: {e}",
                extra={"extra_data": {"error": str(e)}},
            )

    def validate_and_extract_interests(self, interests) -> Tuple[Optional[List], Optional[List]]:
        """
        Validate interests structure and extract topics and counts.

        Args:
            interests: Interest data in format [["Topic1", "Topic2"], [1, 2]]

        Returns:
            tuple: (topics, counts) or (None, None) if invalid
        """
        if not interests or not isinstance(interests, (list, tuple)) or len(interests) != 2:
            return None, None

        topics = interests[0]
        counts = interests[1]

        if not topics or not counts or not isinstance(topics, list) or not isinstance(counts, list):
            return None, None

        if len(topics) == 0:
            return None, None

        return topics, counts

    def _get_agent_config_file(self) -> Optional[Path]:
        """Get the agent population configuration file path."""
        client_specific = self.config_path / f"{self.client_id}_agent_population.json"
        generic = self.config_path / "agent_population.json"

        if client_specific.exists():
            return client_specific
        elif generic.exists():
            return generic
        else:
            return None
