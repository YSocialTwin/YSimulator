"""
Churn Manager Module for YClient.

This module handles churn evaluation and new agent creation for the simulation.
"""

import logging
import random
import uuid
from typing import Dict, List

import ray
from faker import Faker

from YSimulator.YClient.classes.ray_models import AgentProfile


def evaluate_churn(
    server,
    client_id: str,
    agent_profiles: List[AgentProfile],
    churn_enabled: bool,
    churn_probability: float,
    inactivity_threshold: int,
    churn_percentage: float,
    logger: logging.Logger,
) -> Dict[str, int]:
    """
    Evaluate and process churn at the end of a day (client-side).

    This method:
    1. Gets current day and round from server
    2. Identifies inactive agents based on inactivity_threshold
    3. Selects a percentage of them based on churn_percentage
    4. Flags them as churned based on churn_probability

    Args:
        server: Ray server actor handle
        client_id: Client identifier
        agent_profiles: List of agent profiles
        churn_enabled: Whether churn is enabled
        churn_probability: Probability of churning a candidate
        inactivity_threshold: Days of inactivity to be considered for churn
        churn_percentage: Percentage of inactive agents to consider
        logger: Logger instance

    Returns:
        Dictionary with churn statistics
    """
    logger.info(
        f"Starting churn evaluation (client-side): enabled={churn_enabled}, threshold={inactivity_threshold}"
    )

    if not churn_enabled:
        logger.info("Churn disabled, skipping evaluation")
        return {"inactive_agents": 0, "candidates": 0, "churned": 0}

    # Get current day and round ID from server
    try:
        current_day = ray.get(server.get_current_day.remote())
        current_round_id = ray.get(server.get_current_round_id.remote())
    except Exception as e:
        logger.error(f"Failed to get current day/round from server: {e}")
        return {"inactive_agents": 0, "candidates": 0, "churned": 0}

    # Get inactive agents from server database
    try:
        inactive_agents = ray.get(
            server.get_inactive_agents.remote(current_day, inactivity_threshold)
        )
    except Exception as e:
        logger.error(f"Failed to get inactive agents: {e}")
        return {"inactive_agents": 0, "candidates": 0, "churned": 0}

    logger.info(
        f"Found {len(inactive_agents)} inactive agents (threshold={inactivity_threshold} days)"
    )

    if not inactive_agents:
        logger.info("No inactive agents found, skipping churn")
        return {"inactive_agents": 0, "candidates": 0, "churned": 0}

    # Select percentage of inactive agents as churn candidates
    num_candidates = max(1, int(len(inactive_agents) * churn_percentage))
    churn_candidates = random.sample(inactive_agents, min(num_candidates, len(inactive_agents)))

    logger.info(
        f"Selected {len(churn_candidates)} churn candidates (percentage={churn_percentage})"
    )

    # Churn agents based on probability
    churned_count = 0
    agents_to_churn = []  # Collect agents to churn for batch operation

    for agent_id in churn_candidates:
        # Use random for stochastic churn decision
        if random.random() < churn_probability:
            agents_to_churn.append(agent_id)

    # Batch churn all selected agents in a single server call
    if agents_to_churn:
        try:
            logger.info(f"Batch churning {len(agents_to_churn)} agents at round {current_round_id}")
            churned_count = ray.get(
                server.set_agents_churned_batch.remote(agents_to_churn, current_round_id)
            )

            logger.info(
                f"Successfully churned {churned_count} agents in batch",
                extra={
                    "extra_data": {
                        "churned_agent_ids": agents_to_churn,
                        "day": current_day,
                        "round_id": current_round_id,
                    }
                },
            )

            # Update local agent profiles for all churned agents
            for agent_id in agents_to_churn:
                for agent in agent_profiles:
                    if agent.id == agent_id:
                        agent.left_on = current_round_id
                        break

        except Exception as e:
            logger.error(
                f"Failed to batch churn {len(agents_to_churn)} agents: {e}",
                extra={"extra_data": {"error": str(e), "num_agents": len(agents_to_churn)}},
            )
            churned_count = 0

    result = {
        "inactive_agents": len(inactive_agents),
        "candidates": len(churn_candidates),
        "churned": churned_count,
    }

    logger.info(f"Churn evaluation completed: {result}")

    return result


def evaluate_new_agents(
    server,
    client_id: str,
    agent_profiles: List[AgentProfile],
    current_round_id: str,
    new_agents_enabled: bool,
    probability_new_agents: float,
    percentage_new_agents: float,
    logger: logging.Logger,
    add_agent_to_population_file_func,
) -> int:
    """
    Evaluate and add new agents at the end of a day.

    This method:
    1. Counts non-churned agents
    2. Calculates x = percentage_new_agents * non_churned_agents
    3. Adds x new agents, each with probability probability_new_agents
    4. New agent is a copy of an existing agent with unique name
    5. Adds to database and agent_population.json
    6. Sets joined_on to current round

    Args:
        server: Ray server actor handle
        client_id: Client identifier
        agent_profiles: List of agent profiles
        current_round_id: Current round ID (UUID string)
        new_agents_enabled: Whether new agents are enabled
        probability_new_agents: Probability of adding each slot
        percentage_new_agents: Percentage of non-churned agents for slots
        logger: Logger instance
        add_agent_to_population_file_func: Function to add agent to population file

    Returns:
        int: Number of new agents added
    """
    logger.info(
        f"Starting new agents evaluation: enabled={new_agents_enabled}, "
        f"probability={probability_new_agents}, percentage={percentage_new_agents}"
    )

    if not new_agents_enabled:
        logger.info("New agents disabled, skipping evaluation")
        return 0

    # Get non-churned agents (agents without left_on set)
    non_churned_agents = [agent for agent in agent_profiles if agent.left_on is None]

    logger.info(
 f"Non-churned agents: {len(non_churned_agents)}out of {len(agent_profiles)}total (churned: {len(agent_profiles) - len(non_churned_agents)})"
    )

    if not non_churned_agents:
        logger.warning("No non-churned agents available to use as templates for new agents")
        return 0

    # Calculate x = percentage_new_agents * non_churned_agents
    x = int(len(non_churned_agents) * percentage_new_agents)

    logger.info(
        f"Calculated x={x} new agent slots (percentage={percentage_new_agents} * {len(non_churned_agents)})"
    )

    if x == 0:
        logger.info("x=0, no new agents will be added")
        return 0

    new_agents_added = 0
    new_agents_to_register = []  # Collect all new agents for batch registration

    logger.info(f"Attempting to add up to {x} new agents with probability {probability_new_agents}")

    # Add x new agents, each with probability probability_new_agents
    for i in range(x):
        # With probability_new_agents, add a new agent
        roll = random.random()
        logger.debug(
            f"New agent slot {i + 1}/{x}: roll={roll:.4f}, threshold={probability_new_agents}"
        )

        if roll < probability_new_agents:
            logger.info(
                f"Creating new agent {i + 1}/{x} (roll {roll:.4f} < {probability_new_agents})"
            )

            # Select a random existing agent as template
            template_agent = random.choice(non_churned_agents)

            # Generate unique ID and name using Faker
            fake = Faker()
            new_agent_id = str(uuid.uuid4())

            # Generate name based on gender
            gender = template_agent.gender
            if gender and gender.lower() in ["male", "m"]:
                new_username = fake.name_male()
            elif gender and gender.lower() in ["female", "f"]:
                new_username = fake.name_female()
            else:
                # If gender is not specified or other, use generic name
                new_username = fake.name()

            # Replace spaces with underscores for username format
            new_username = new_username.replace(" ", "_").replace(".", "")

            # Ensure uniqueness by checking existing usernames
            existing_usernames = {agent.username for agent in agent_profiles}
            # Also check against agents we're about to create
            existing_usernames.update(agent.username for agent in new_agents_to_register)
            base_username = new_username
            counter = 1
            while new_username in existing_usernames:
                new_username = f"{base_username}_{counter}"
                counter += 1

            # Create new agent profile as copy of template
            new_agent = AgentProfile(
                id=new_agent_id,
                username=new_username,
                email=f"{new_username}@simulation.local",
                password=template_agent.password,
                leaning=template_agent.leaning,
                user_type=template_agent.user_type,
                age=template_agent.age,
                oe=template_agent.oe,
                co=template_agent.co,
                ex=template_agent.ex,
                ag=template_agent.ag,
                ne=template_agent.ne,
                language=template_agent.language,
                education_level=template_agent.education_level,
                joined_on=current_round_id,  # Set to current round
                gender=template_agent.gender,
                nationality=template_agent.nationality,
                profession=template_agent.profession,
                activity_profile=template_agent.activity_profile,
                archetype=template_agent.archetype,
                cluster=template_agent.cluster,
                llm=template_agent.llm,
                toxicity=template_agent.toxicity,
                daily_activity_level=template_agent.daily_activity_level,
                round_actions=template_agent.round_actions,
                is_page=0,  # New agents are not pages
                left_on=None,  # New agents are not churned
            )

            # Add to local list and batch registration list
            agent_profiles.append(new_agent)
            new_agents_to_register.append(new_agent)

            logger.debug(
                f"Prepared new agent: {new_username} (template: {template_agent.username})",
                extra={
                    "extra_data": {
                        "new_agent_id": new_agent_id,
                        "template_id": template_agent.id,
                    }
                },
            )
        else:
            logger.debug(
                f"Skipping new agent slot {i + 1}/{x} (roll {roll:.4f} >= {probability_new_agents})"
            )

    # Batch register all new agents with server in a single call
    if new_agents_to_register:
        try:
            logger.info(f"Batch registering {len(new_agents_to_register)} new agents with server")
            _ = ray.get(server.register_agents.remote(new_agents_to_register, client_id=client_id))
            new_agents_added = len(new_agents_to_register)

            logger.info(
                f"Successfully registered {new_agents_added} new agents in batch",
                extra={
                    "extra_data": {
                        "agent_ids": [agent.id for agent in new_agents_to_register],
                        "agent_names": [agent.username for agent in new_agents_to_register],
                    }
                },
            )

            # Update agent_population.json for all new agents
            for new_agent in new_agents_to_register:
                add_agent_to_population_file_func(new_agent)

        except Exception as e:
            logger.error(
                f"Failed to batch register {len(new_agents_to_register)} new agents: {e}",
                extra={"extra_data": {"error": str(e), "num_agents": len(new_agents_to_register)}},
            )
            # Remove failed agents from local list
            for failed_agent in new_agents_to_register:
                if failed_agent in agent_profiles:
                    agent_profiles.remove(failed_agent)
            new_agents_added = 0

    logger.info(
        f"New agents evaluation complete: added {new_agents_added} out of {x} possible slots"
    )
    return new_agents_added
