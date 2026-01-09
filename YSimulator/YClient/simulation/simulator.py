"""
Simulator Module for YClient.

This module contains the main simulation coordinator that orchestrates the simulation loop.
Extracted from client.py's run() method as part of Phase 2 refactoring.

The Simulator coordinates:
- Client and agent registration
- Main simulation loop (day/slot/round progression)
- Heartbeat management
- Lifecycle operations (churn, daily follows, new agents)
- Network loading
- Simulation completion
"""

import logging
import time
from typing import Optional

import ray

from YSimulator.YClient.simulation.agent_scheduler import AgentScheduler
from YSimulator.YClient.simulation.batch_processor import BatchProcessor
from YSimulator.YClient.simulation.lifecycle_manager import LifecycleManager
from YSimulator.YClient.simulation.round_executor import RoundExecutor
from YSimulator.YClient.simulation.secondary_follow_processor import SecondaryFollowProcessor


class Simulator:
    """
    Main simulation coordinator.

    Orchestrates the entire simulation lifecycle:
    1. Registration (agents, client, network)
    2. Main simulation loop
    3. End-of-day lifecycle operations
    4. Completion notification
    """

    def __init__(
        self,
        server,
        client_id: str,
        agent_profiles: list,
        config_path,
        num_days: int,
        num_slots_per_day: int,
        heartbeat_interval: float,
        agent_scheduler: AgentScheduler,
        batch_processor: BatchProcessor,
        lifecycle_manager: LifecycleManager,
        round_executor: RoundExecutor,
        secondary_follow_processor: SecondaryFollowProcessor,
        logger: logging.Logger,
        # Additional functions needed from client
        parse_network_edges_fn,
        load_and_create_social_network_fn,
        create_action_generator_factory_fn,
        log_action_fn,
        log_hourly_summary_fn,
        log_daily_summary_fn,
    ):
        """
        Initialize the Simulator.

        Args:
            server: Ray server actor handle
            client_id: Client identifier
            agent_profiles: List of agent profiles
            config_path: Path to configuration directory
            num_days: Number of days to simulate (0 = infinite)
            num_slots_per_day: Number of time slots per day
            heartbeat_interval: Seconds between heartbeats
            agent_scheduler: AgentScheduler instance
            batch_processor: BatchProcessor instance
            lifecycle_manager: LifecycleManager instance
            round_executor: RoundExecutor instance
            secondary_follow_processor: SecondaryFollowProcessor instance
            logger: Logger instance
            parse_network_edges_fn: Function to parse network edges
            load_and_create_social_network_fn: Function to load network
            create_action_generator_factory_fn: Function to create action generator factory
            log_action_fn: Function to log individual actions
            log_hourly_summary_fn: Function to log hourly summaries
            log_daily_summary_fn: Function to log daily summaries
        """
        self.server = server
        self.client_id = client_id
        self.agent_profiles = agent_profiles
        self.config_path = config_path
        self.num_days = num_days
        self.num_slots_per_day = num_slots_per_day
        self.heartbeat_interval = heartbeat_interval
        self.agent_scheduler = agent_scheduler
        self.batch_processor = batch_processor
        self.lifecycle_manager = lifecycle_manager
        self.round_executor = round_executor
        self.secondary_follow_processor = secondary_follow_processor
        self.logger = logger
        self.parse_network_edges_fn = parse_network_edges_fn
        self.load_and_create_social_network_fn = load_and_create_social_network_fn
        self.create_action_generator_factory_fn = create_action_generator_factory_fn
        self.log_action_fn = log_action_fn
        self.log_hourly_summary_fn = log_hourly_summary_fn
        self.log_daily_summary_fn = log_daily_summary_fn

    def run(self, calculate_opinion_updates_fn) -> None:
        """
        Main simulation loop for the client.

        This method:
        1. Registers agents with the server
        2. Registers the client
        3. Loads social network if available
        4. Runs the simulation loop until completion or max days reached
        5. Sends periodic heartbeats to prevent being marked as stale
        6. Notifies server on completion

        Args:
            calculate_opinion_updates_fn: Function to calculate opinion updates
        """
        # Register agents with the server
        start_time = time.time()
        self.logger.info(f" Registering {len(self.agent_profiles)} agents with server...")

        registration_result = ray.get(
            self.server.register_agents.remote(self.agent_profiles, client_id=self.client_id)
        )
        reg_time = (time.time() - start_time) * 1000

        self.logger.info(
            "Agents registered with server",
            extra={"extra_data": {**registration_result, "execution_time_ms": reg_time}},
        )
        self.logger.info(f" Agent registration complete: {registration_result}")

        # Register client with the server, passing num_days for informational purposes
        client_reg = ray.get(self.server.register_client.remote(self.client_id, self.num_days))

        # Validate registration response has all required fields
        required_fields = ["registered", "start_day", "start_slot"]
        if not isinstance(client_reg, dict):
            raise RuntimeError(f"Client registration failed: expected dict, got {type(client_reg)}")

        missing_fields = [f for f in required_fields if f not in client_reg]
        if missing_fields:
            raise RuntimeError(f"Client registration response missing fields: {missing_fields}")

        if not client_reg["registered"]:
            raise RuntimeError(f"Client registration failed: {client_reg}")

        # Server tells us where to start - we count from here
        start_day = client_reg["start_day"]
        start_slot = client_reg["start_slot"]

        # Load social network if available
        self._load_network_if_available()

        # Calculate our personal max_day for local tracking
        # num_days=0 means infinite simulation
        max_day = start_day + self.num_days if self.num_days > 0 else float("inf")
        max_day_str = "∞" if max_day == float("inf") else str(max_day)

        self.logger.info(
            "Client registered with server",
            extra={
                "extra_data": {
                    "start_day": start_day,
                    "start_slot": start_slot,
                    "num_days": self.num_days,
                    "max_day": max_day,
                }
            },
        )
        self.logger.info(
            f"[{self.client_id}] Client registered. Starting at day {start_day}, slot {start_slot}. "
            f"Will run for {self.num_days if self.num_days > 0 else '∞'} days (until day {max_day_str})."
        )

        slot_count = 0
        last_heartbeat_time = time.time()

        # Track active agents per day for daily follow evaluation
        current_day = start_day
        active_agents_today = set()  # Set of agent IDs active during current day

        try:
            while True:
                # Send heartbeat periodically (configurable interval, default: 5 seconds)
                if time.time() - last_heartbeat_time > self.heartbeat_interval:
                    ray.get(self.server.heartbeat.remote(self.client_id))
                    last_heartbeat_time = time.time()

                instruction = ray.get(self.server.get_instruction.remote(self.client_id))

                if instruction.status == "WAIT":
                    time.sleep(1)
                    continue

                # Check if we've reached our personal maximum day (client-side tracking)
                if self.num_days > 0 and instruction.day >= max_day:
                    self.logger.info(
                        "Reached maximum days (client-side check)",
                        extra={
                            "extra_data": {
                                "final_day": instruction.day,
                                "start_day": start_day,
                                "num_days": self.num_days,
                                "total_slots": slot_count,
                            }
                        },
                    )
                    self.logger.info(
                        f"[{self.client_id}] Completed {self.num_days} days "
                        f"(day {start_day} to {instruction.day - 1}). Total slots: {slot_count}"
                    )
                    break

                # Process simulation round
                sim_start = time.time()
                actions, active_agent_ids = self._simulate_round(
                    instruction.day,
                    instruction.slot,
                    instruction.recent_post_ids,
                    calculate_opinion_updates_fn,
                )
                sim_time = (time.time() - sim_start) * 1000

                # Track active agents for this day
                active_agents_today.update(active_agent_ids)

                # Check if this is the last slot of the day (end of day)
                is_last_slot = instruction.slot == self.num_slots_per_day - 1
                day_changed = instruction.day != current_day

                # Handle end-of-day operations
                if is_last_slot or day_changed:
                    actions.extend(
                        self._handle_end_of_day(
                            current_day, instruction.day, active_agents_today, is_last_slot
                        )
                    )
                    # Reset for next day
                    active_agents_today = set()
                    current_day = instruction.day

                # Log actions
                self._log_actions(actions, instruction.day, instruction.slot, sim_time)

                # Log summaries
                self.log_hourly_summary_fn(instruction.day, instruction.slot)
                if is_last_slot:
                    self.log_daily_summary_fn(instruction.day)

                # Submit actions
                submit_start = time.time()
                ray.get(self.server.submit_actions.remote(self.client_id, actions))
                submit_time = (time.time() - submit_start) * 1000

                slot_count += 1

                self.logger.info(
                    "Slot completed",
                    extra={
                        "extra_data": {
                            "day": instruction.day,
                            "slot": instruction.slot,
                            "num_actions": len(actions),
                            "simulation_time_ms": sim_time,
                            "submit_time_ms": submit_time,
                        }
                    },
                )

                self.logger.info(
                    f"[{self.client_id}] Day {instruction.day} Slot {instruction.slot} -> "
                    f"Submitted {len(actions)} actions."
                )

        finally:
            # Notify server that this client has completed all activities
            try:
                ray.get(self.server.complete_client.remote(self.client_id))
                self.logger.info("Notified server of completion")
                self.logger.info(f" Simulation complete. Server notified.")
            except Exception as e:
                self.logger.warning(
                    f"Failed to notify server of completion: {e}",
                    extra={"extra_data": {"error": str(e)}},
                )

    def _load_network_if_available(self):
        """
        Load social network topology from network.csv if available.
        """
        # Check if we should load the social network topology from network.csv
        # This works regardless of when the client joins (multi-client scenarios)
        # Try client-specific network file first, then fall back to generic
        network_csv_path = self.config_path / f"{self.client_id}_network.csv"
        if not network_csv_path.exists():
            network_csv_path = self.config_path / "network.csv"

        if network_csv_path.exists():
            # First, parse the network edges from CSV
            self.logger.info(
                f"[{self.client_id}] Checking if social network needs to be loaded from {network_csv_path.name}..."
            )
            edges = self.parse_network_edges_fn(network_csv_path)

            if edges:
                # Ask server if any of these edges already exist in the database
                edges_exist = ray.get(self.server.check_network_edges_exist.remote(edges))

                if not edges_exist:
                    self.logger.info(
                        f"[{self.client_id}] Loading social network topology from {network_csv_path.name}..."
                    )
                    self.load_and_create_social_network_fn(network_csv_path)
                else:
                    self.logger.info("Network already loaded (edges exist in database)")
                    self.logger.info(f" Social network already loaded, skipping")
            else:
                self.logger.warning(f"No valid edges found in {network_csv_path.name}")
        else:
            self.logger.info("No network.csv found, skipping social network creation")

    def _simulate_round(
        self, day: int, slot: int, recent_posts: list, calculate_opinion_updates_fn
    ):
        """
        Simulate agent behaviors for a given time slot.

        Args:
            day: Current simulation day
            slot: Current time slot (0-23, representing hour of day)
            recent_posts: List of recent post UUIDs for reactions
            calculate_opinion_updates_fn: Function to calculate opinion updates

        Returns:
            Tuple of (actions, active_agent_ids)
        """
        # Select active agents for this slot
        regular_agents, page_agents = self.agent_scheduler.select_active_agents(slot)
        active_agents = regular_agents + page_agents

        # Create action generator factory
        action_generator_factory = self.create_action_generator_factory_fn(day, slot, recent_posts)

        # Execute round (scatter phase)
        (
            actions,
            pending_llm_posts,
            pending_llm_reactions,
            pending_llm_follows,
            rule_based_interactions,
        ) = self.round_executor.execute_round(active_agents, recent_posts, action_generator_factory)

        # Gather phase: Wait for all LLM results in parallel
        self.logger.info(
            f"Gather phase: pending_llm_posts={len(pending_llm_posts)}, "
            f"pending_llm_reactions={len(pending_llm_reactions)}, "
            f"pending_llm_follows={len(pending_llm_follows)}, "
            f"actions_so_far={len(actions)}"
        )

        # Gather LLM posts
        self.batch_processor.gather_pending_llm_posts(pending_llm_posts, actions)

        # Gather LLM reactions and track interactions for secondary follow
        secondary_follow_candidates = self.batch_processor.gather_pending_llm_reactions(
            pending_llm_reactions, actions, calculate_opinion_updates_fn
        )

        # Gather LLM follows
        self.batch_processor.gather_pending_llm_follows(pending_llm_follows, actions)

        # Process secondary follows using SecondaryFollowProcessor (Phase 1 alignment)
        self.secondary_follow_processor.process_secondary_follows(
            secondary_follow_candidates, rule_based_interactions, actions
        )

        self.logger.info(
            f"Returning {len(actions)} total actions, {len(active_agents)} active agents"
        )
        return actions, {agent.id for agent in active_agents}

    def _handle_end_of_day(
        self, current_day: int, instruction_day: int, active_agents_today: set, is_last_slot: bool
    ) -> list:
        """
        Handle end-of-day lifecycle operations.

        Args:
            current_day: Current day being tracked
            instruction_day: Day from instruction
            active_agents_today: Set of agent IDs active today
            is_last_slot: Whether this is the last slot of the day

        Returns:
            List of additional actions (daily follows)
        """
        additional_actions = []

        # Evaluate daily follows at the end of each day
        if self.lifecycle_manager.probability_of_daily_follow > 0 and active_agents_today:
            self.logger.info(
                f"End of day {current_day}: Evaluating daily follows for {len(active_agents_today)} active agents, "
                f"probability={self.lifecycle_manager.probability_of_daily_follow}"
            )
            daily_follow_actions = self.lifecycle_manager.evaluate_daily_follows(
                active_agents_today, instruction_day
            )
            if daily_follow_actions:
                additional_actions.extend(daily_follow_actions)
                self.logger.info(f"Added {len(daily_follow_actions)} daily follow actions")

        # Evaluate churn at the end of each day
        if self.lifecycle_manager.churn_enabled:
            try:
                self.logger.info(
                    f"End of day {current_day}: Evaluating churn (enabled={self.lifecycle_manager.churn_enabled})"
                )
                churn_stats = self.lifecycle_manager.evaluate_churn()
                self.logger.info(
                    f"Churn evaluation complete: inactive={churn_stats['inactive_agents']}, "
                    f"candidates={churn_stats['candidates']}, churned={churn_stats['churned']}"
                )
                if churn_stats["churned"] > 0:
                    self.logger.info(
                        f"Churn evaluation: {churn_stats['churned']} agents churned out of "
                        f"{churn_stats['candidates']} candidates ({churn_stats['inactive_agents']} inactive)"
                    )
                    # Invalidate churned agents cache after new churns
                    self.agent_scheduler.invalidate_churn_cache()
            except Exception as e:
                self.logger.error(
                    f"Error evaluating churn: {e}",
                    extra={"extra_data": {"error": str(e)}},
                )

        # Evaluate new agents at the end of each day
        if self.lifecycle_manager.new_agents_enabled:
            try:
                self.logger.info(
                    f"End of day {current_day}: Evaluating new agents (enabled={self.lifecycle_manager.new_agents_enabled})"
                )
                # Get current round_id from server
                current_round_id = ray.get(self.server.get_current_round_id.remote())
                new_agents_count = self.lifecycle_manager.evaluate_new_agents(current_round_id)
                self.logger.info(f"New agents evaluation complete: {new_agents_count} agents added")
                if new_agents_count > 0:
                    self.logger.info(
                        f"New agents evaluation: {new_agents_count} agents added to population"
                    )
            except Exception as e:
                self.logger.error(
                    f"Error evaluating new agents: {e}",
                    extra={"extra_data": {"error": str(e)}},
                )

        # At end of day, save updated agent interests from server
        try:
            self.lifecycle_manager.save_updated_agent_interests()
        except Exception as e:
            self.logger.error(
                f"Error saving updated agent interests: {e}",
                extra={"extra_data": {"error": str(e)}},
            )

        return additional_actions

    def _log_actions(self, actions: list, day: int, slot: int, sim_time: float):
        """
        Log individual actions before submission.

        Args:
            actions: List of actions to log
            day: Current day
            slot: Current slot
            sim_time: Simulation time in milliseconds
        """
        for action in actions:
            # Get agent username from agent_id
            agent_profile = next((a for a in self.agent_profiles if a.id == action.agent_id), None)
            agent_name = agent_profile.username if agent_profile else str(action.agent_id)

            # Normalize action type to method name (lowercase)
            method_name = action.action_type.lower()

            # Estimate execution time based on simulation time divided by number of actions
            # This is an approximation since we don't track individual action times
            execution_time = (sim_time / 1000.0) / len(actions) if len(actions) > 0 else 0

            # All actions that reach this point are considered successful
            self.log_action_fn(
                agent_name,
                method_name,
                execution_time,
                True,
                day,
                slot,
            )
