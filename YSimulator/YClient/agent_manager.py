"""
Agent Manager Module for YClient.

This module handles agent lifecycle management including agent creation,
loading network edges, and agent population tracking.
"""

import csv
import json
import logging
import random
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import ray

from YSimulator.YClient.classes.ray_models import AgentProfile


def create_agents_from_config(agent_config: dict, logger: logging.Logger) -> List[AgentProfile]:
    """
    Create agent profiles from configuration.
    Combines predefined agents with generated agents.

    Args:
        agent_config: Agent configuration dictionary
        logger: Logger instance

    Returns:
        List of AgentProfile objects
    """
    agents = []

    # Load predefined agents
    if "agents" in agent_config:
        for agent_data in agent_config["agents"]:
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
                recsys_type=agent_data.get("recsys_type", "random"),  # Content recommendation mode
                frecsys_type=agent_data.get(
                    "frecsys_type", "default"
                ),  # Follow recommendation mode
                language=agent_data.get("language", "en"),
                education_level=agent_data.get("education_level"),
                joined_on=agent_data.get("joined_on"),  # Should be Round UUID or None
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
                feed_url=agent_data.get("feed_url"),  # RSS feed for page agents
                interests=agent_data.get("interests"),  # Interest topics and counts
                opinions=agent_data.get("opinions"),  # Opinion values for topics
                stubborn_topics=agent_data.get("stubborn_topics"),
                custom_features=agent_data.get("custom_features"),
            )
            agents.append(profile)

    # Generate additional agents if specified
    if "generation_config" in agent_config:
        gen_config = agent_config["generation_config"]
        num_additional = gen_config.get("num_additional_agents", 0)
        cluster_weights = gen_config["cluster_distribution"]["weights"]
        llm_prob = gen_config.get("llm_enabled_probability", 0.1)
        defaults = gen_config.get("default_settings", {})
        age_range = gen_config.get("age_range", [18, 65])

        # Generate UUIDs for additional agents using the same namespace
        AGENT_UUID_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")

        # Find the starting index for generated agents
        # If we have predefined agents, start after them; otherwise start at 1
        if agents:
            # Try to extract numeric part from existing IDs for indexing
            # For UUIDs, we'll just start from a high number to avoid conflicts
            start_index = 10000
        else:
            start_index = 1

        archetypes = ["validator", "broadcaster", "explorer"]
        activity_profiles = ["Always On", "Morning Active", "Evening Active", "Weekend Warrior"]
        professions = ["Engineer", "Teacher", "Designer", "Writer", "Analyst", "Manager"]
        genders = ["male", "female", "non-binary"]
        nationalities = ["US", "UK", "CA", "AU", "EU"]
        education_levels = ["high_school", "college", "graduate", "phd"]

        for i in range(num_additional):
            agent_index = start_index + i
            # Generate deterministic UUID for generated agents
            agent_id = str(uuid.uuid5(AGENT_UUID_NAMESPACE, f"generated_agent_{agent_index}"))
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
                joined_on=None,  # Will be set by server to current round on registration
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


def parse_network_edges(network_csv_path: Path, logger: logging.Logger) -> List[Tuple[str, str]]:
    """
    Parse network edges from CSV file.

    Args:
        network_csv_path: Path to network edges CSV file
        logger: Logger instance

    Returns:
        list: List of (source_id, target_id) tuples representing follow relationships
    """
    edges = []

    if not network_csv_path.exists():
        logger.error(f"Network edges file not found: {network_csv_path}")
        return edges

    try:
        with open(network_csv_path, "r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)

            # Validate required columns
            if "source" not in reader.fieldnames or "target" not in reader.fieldnames:
                logger.error(
                    f"Network CSV must contain 'source' and 'target' columns. Found: {reader.fieldnames}"
                )
                return edges

            for row in reader:
                source = row["source"].strip()
                target = row["target"].strip()

                if not source or not target:
                    logger.warning(f"Skipping invalid edge: source='{source}', target='{target}'")
                    continue

                edges.append((source, target))

        logger.info(f"Parsed {len(edges)} network edges from {network_csv_path}")

    except Exception as e:
        logger.error(f"Error parsing network edges file: {e}")

    return edges


def load_and_create_social_network(
    network_csv_path: Path, server, client_id: str, logger: logging.Logger, batch_size: int = 100
) -> int:
    """
    Load network edges from CSV and create follow relationships on server.

    Args:
        network_csv_path: Path to network edges CSV file
        server: Ray server actor handle
        client_id: Client identifier
        logger: Logger instance
        batch_size: Number of edges to process in each batch (default: 100)

    Returns:
        int: Number of follow relationships successfully created
    """
    edges = parse_network_edges(network_csv_path, logger)

    if not edges:
        logger.warning("No edges to create")
        return 0

    # Create follow relationships in batches
    success_count = 0
    failed_count = 0

    for i in range(0, len(edges), batch_size):
        batch = edges[i : i + batch_size]

        try:
            # Send batch to server
            result = ray.get(
                server.create_follow_relationships_batch.remote(batch, client_id=client_id)
            )

            if result:
                success_count += len(batch)
                logger.info(
                    f"Successfully created {len(batch)} follow relationships "
                    f"(batch {i // batch_size + 1}/{(len(edges) + batch_size - 1) // batch_size})"
                )
            else:
                failed_count += len(batch)
                logger.warning(
                    f"Failed to create batch of {len(batch)} follow relationships "
                    f"(batch {i // batch_size + 1}/{(len(edges) + batch_size - 1) // batch_size})"
                )

        except Exception as e:
            failed_count += len(batch)
            logger.error(
                f"Error creating follow relationships batch: {e}",
                extra={"extra_data": {"batch_size": len(batch), "error": str(e)}},
            )

    logger.info(
        f"Network creation complete: {success_count}successful, {failed_count}failed out of {len(edges)}total edges"
    )

    return success_count


def extract_agent_attrs(
    agent: AgentProfile,
    validate_and_extract_interests_func,
    is_opinion_dynamics_enabled_func,
    map_opinion_to_group_func,
) -> dict:
    """
    Extract agent attributes for dynamic persona building.

    Args:
        agent: AgentProfile object
        validate_and_extract_interests_func: Function to validate and extract interests
        is_opinion_dynamics_enabled_func: Function to check if opinion dynamics is enabled
        map_opinion_to_group_func: Function to map opinion values to groups

    Returns:
        dict: Agent attributes for persona template
    """
    # Sample a topic from agent's interests if available
    selected_topic = None
    topics, counts = validate_and_extract_interests_func(agent.interests)
    if topics and counts:
        # Weight topics by their interaction counts
        selected_topic = random.choices(topics, weights=counts, k=1)[0]

    # Get opinion on the selected topic if available (only if opinion dynamics is enabled)
    topic_opinion = None
    topic_opinion_label = None
    if (
        is_opinion_dynamics_enabled_func()
        and selected_topic
        and agent.opinions
        and selected_topic in agent.opinions
    ):
        topic_opinion = agent.opinions[selected_topic]
        topic_opinion_label = map_opinion_to_group_func(topic_opinion)

    attrs = {
        "name": agent.username,
        "age": agent.age if agent.age else "unknown",
        "gender": agent.gender if agent.gender else "person",
        "nationality": agent.nationality if agent.nationality else "citizen",
        "profession": agent.profession if agent.profession else "individual",
        "political_leaning": agent.leaning if agent.leaning else "neutral",
        "oe": agent.oe if agent.oe else "average in openness",
        "co": agent.co if agent.co else "average in conscientiousness",
        "ex": agent.ex if agent.ex else "average in extraversion",
        "ag": agent.ag if agent.ag else "average in agreeableness",
        "ne": agent.ne if agent.ne else "average in neuroticism",
        "toxicity": agent.toxicity if agent.toxicity and agent.toxicity != "" else "no",
        "topic": selected_topic,  # Include the sampled topic
        "custom_features": dict(agent.custom_features or {}),
    }

    # Add opinion information if available and opinion dynamics is enabled
    if topic_opinion is not None and topic_opinion_label:
        attrs["topic_opinion"] = topic_opinion_label
        attrs["topic_opinion_value"] = topic_opinion

    return attrs


def save_updated_agent_population(
    updated_interests: Dict[str, Dict[str, List]],
    config_path: Path,
    client_id: str,
    logger: logging.Logger,
):
    """
    Save updated agent interests to agent_population.json at end of day.
    Respects client-specific naming convention (e.g., client_1_agent_population.json).

    Args:
        updated_interests: Dict of {agent_id: {"topics": [...], "counts": [...]}}
        config_path: Path to configuration directory
        client_id: Client identifier
        logger: Logger instance
    """
    # Find agent_population.json file using client-specific naming convention
    # Try client-specific file first, then fall back to generic
    client_specific_file = config_path / f"{client_id}_agent_population.json"
    generic_file = config_path / "agent_population.json"

    if client_specific_file.exists():
        agent_config_file = client_specific_file
    else:
        agent_config_file = generic_file

    if not agent_config_file.exists():
        logger.warning(
            f"Agent config file not found at {agent_config_file}, skipping interests update"
        )
        return

    try:
        # Load current agent_population.json
        with open(agent_config_file, "r") as f:
            agent_data = json.load(f)

        # Update interests for each agent
        if "agents" in agent_data:
            for agent in agent_data["agents"]:
                agent_id = agent.get("id")
                if agent_id and str(agent_id) in updated_interests:
                    interests_data = updated_interests[str(agent_id)]
                    # Update the interests field with current topics and counts
                    agent["interests"] = [interests_data["topics"], interests_data["counts"]]

        # Write updated data back to file
        with open(agent_config_file, "w") as f:
            json.dump(agent_data, f, indent=2)

        logger.info(
            f"Updated {agent_config_file.name}with current interests for {len(updated_interests)}agents"
        )

    except Exception as e:
        logger.error(
            f"Error updating agent population file: {e}",
            extra={"extra_data": {"error": str(e), "file": str(agent_config_file)}},
        )


def validate_and_extract_interests(interests) -> Tuple[Optional[List], Optional[List]]:
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


def add_agent_to_population_file(
    agent: AgentProfile, config_path: Path, client_id: str, logger: logging.Logger
):
    """
    Add a new agent to the agent_population.json file.

    Args:
        agent: AgentProfile to add to the file
        config_path: Path to configuration directory
        client_id: Client identifier
        logger: Logger instance
    """
    # Find agent_population.json file using client-specific naming convention
    client_specific_file = config_path / f"{client_id}_agent_population.json"
    generic_file = config_path / "agent_population.json"

    if client_specific_file.exists():
        agent_config_file = client_specific_file
    else:
        agent_config_file = generic_file

    if not agent_config_file.exists():
        logger.warning(
            f"Agent config file not found at {agent_config_file}, skipping agent addition to file"
        )
        return

    try:
        # Load current agent_population.json
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

        # Write updated data back to file
        with open(agent_config_file, "w") as f:
            json.dump(agent_data, f, indent=2)

        logger.info(f"Added agent {agent.username} to {agent_config_file.name}")

    except Exception as e:
        logger.error(
            f"Error adding agent to population file: {e}",
            extra={"extra_data": {"error": str(e), "file": str(agent_config_file)}},
        )
