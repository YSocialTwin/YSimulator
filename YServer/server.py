"""
YServer - Orchestrator Server for YSimulator.

This module contains the Ray remote actor that orchestrates the simulation,
managing client registration, agent actions, and simulation state progression.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import ray

from classes.ray_models import SimulationInstruction


@ray.remote
class OrchestratorServer:
    """
    Orchestrator server actor that manages simulation state and coordinates clients.

    This server handles:
    - Client registration and deregistration
    - Agent profile registration in the database
    - Simulation state progression (days and slots)
    - Action submission and processing
    - Barrier synchronization between clients
    """

    def __init__(
        self,
        db_config: dict,
        config_path: str = ".",
        min_to_start: int = 1,
        server_name: str = "orchestrator",
        redis_config: dict = None,
        timeout_seconds: int = 60,
    ):
        """
        Initialize the orchestrator server.

        Args:
            db_config: Database configuration dict with type and connection details
            config_path: Path to configuration directory for logs
            min_to_start: Minimum number of clients before simulation starts
            server_name: Name of this server instance (str)
            redis_config: Redis configuration dict (optional)
            timeout_seconds: Seconds before considering a client stale (default: 60)
        """
        from classes.db_middleware import DatabaseMiddleware

        # Server configuration
        self.min_to_start = min_to_start
        self.server_name = server_name
        self.config_path = Path(config_path)
        self.timeout_seconds = timeout_seconds

        # Client tracking
        self.registered_clients = set()  # All registered clients
        self.completed_clients = set()  # Clients that finished their simulation
        self.submitted_clients = set()  # Clients that submitted for current slot
        self.last_heartbeat = {}  # {client_id: timestamp}
        self.registered_agents = {}  # {agent_id: username}

        # Simulation state
        self.day = 1
        self.slot = 1
        self.recent_posts_cache = []

        # Set up logging first
        self._setup_logging()

        # Initialize database middleware
        self.db = DatabaseMiddleware(
            db_config=db_config,
            config_path=str(self.config_path),
            redis_config=redis_config,
            logger=self.logger,
        )

        self.logger.info(
            "Orchestrator server initialized",
            extra={
                "extra_data": {
                    "db_type": db_config.get("type", "sqlite"),
                    "min_to_start": min_to_start,
                    "redis_enabled": self.db.use_redis,
                    "timeout_seconds": timeout_seconds,
                }
            },
        )

    def _setup_logging(self):
        """Set up JSON logging for the server actor."""
        log_dir = self.config_path / "logs"
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / f"{self.server_name}_actor.log"

        # Create logger
        self.logger = logging.getLogger(f"YSimulator.Server.{self.server_name}")
        self.logger.setLevel(logging.INFO)

        # Remove existing handlers
        self.logger.handlers = []

        # Create file handler with JSON formatting
        from logging.handlers import RotatingFileHandler

        handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)  # 10MB

        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_data = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "level": record.levelname,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                }
                if hasattr(record, "execution_time"):
                    log_data["execution_time_ms"] = record.execution_time
                if hasattr(record, "extra_data"):
                    log_data.update(record.extra_data)
                return json.dumps(log_data)

        handler.setFormatter(JsonFormatter())
        self.logger.addHandler(handler)

    def register_agents(self, agents: list) -> dict:
        """
        Register agent profiles in the database if they don't already exist.

        Args:
            agents: List of AgentProfile dataclass instances

        Returns:
            dict: Summary of registration results with counts
        """
        start_time = time.time()
        registered_count = 0
        skipped_count = 0

        try:
            for agent_profile in agents:
                # Prepare user data
                joined_on = agent_profile.joined_on
                if joined_on == 0:
                    joined_on = int(time.time())

                user_data = {
                    "id": agent_profile.id,
                    "username": agent_profile.username,
                    "email": agent_profile.email,
                    "password": agent_profile.password,
                    "leaning": agent_profile.leaning,
                    "user_type": agent_profile.user_type,
                    "age": agent_profile.age,
                    "oe": agent_profile.oe,
                    "co": agent_profile.co,
                    "ex": agent_profile.ex,
                    "ag": agent_profile.ag,
                    "ne": agent_profile.ne,
                    "recsys_type": agent_profile.recsys_type,
                    "frecsys_type": agent_profile.frecsys_type,
                    "language": agent_profile.language,
                    "owner": agent_profile.owner,
                    "education_level": agent_profile.education_level,
                    "joined_on": joined_on,
                    "gender": agent_profile.gender,
                    "nationality": agent_profile.nationality,
                    "round_actions": agent_profile.round_actions,
                    "toxicity": agent_profile.toxicity,
                    "is_page": agent_profile.is_page,
                    "left_on": agent_profile.left_on,
                    "daily_activity_level": agent_profile.daily_activity_level,
                    "profession": agent_profile.profession,
                    "activity_profile": agent_profile.activity_profile,
                    "archetype": agent_profile.archetype,
                }

                # Try to register user
                if self.db.register_user(user_data):
                    registered_count += 1
                    self.registered_agents[agent_profile.id] = agent_profile.username
                else:
                    skipped_count += 1
                    self.registered_agents[agent_profile.id] = agent_profile.username

            execution_time = (time.time() - start_time) * 1000

            self.logger.info(
                "Agent registration complete",
                extra={
                    "extra_data": {
                        "registered": registered_count,
                        "skipped": skipped_count,
                        "total": len(self.registered_agents),
                        "execution_time_ms": execution_time,
                    }
                },
            )

            print(
                f"[Server] 👥 Agent Registration: {registered_count} new, {skipped_count} existing"
            )

            return {
                "registered": registered_count,
                "skipped": skipped_count,
                "total": len(self.registered_agents),
            }

        except Exception as e:
            self.logger.error(
                f"Agent registration error: {e}", extra={"extra_data": {"error": str(e)}}
            )
            print(f"[Server] ❌ Agent registration error: {e}")
            raise

    def register_client(self, client_id: str) -> bool:
        """
        Register a new client with the server.

        Dynamic Registration: New clients can join anytime. They effectively 'pause' the
        current slot until they catch up and submit their action.

        Args:
            client_id: Unique identifier for the client

        Returns:
            bool: True if registration successful
        """
        start_time = time.time()

        if client_id not in self.registered_clients:
            self.registered_clients.add(client_id)
            self.last_heartbeat[client_id] = time.time()
            execution_time = (time.time() - start_time) * 1000

            self.logger.info(
                "Client registered",
                extra={
                    "extra_data": {
                        "client_id": client_id,
                        "total_clients": len(self.registered_clients),
                        "active_clients": len(self._get_active_clients()),
                        "execution_time_ms": execution_time,
                    }
                },
            )
            print(
                f"[Server] 🟢 Client {client_id} joined. "
                f"Total: {len(self.registered_clients)}, "
                f"Active: {len(self._get_active_clients())}"
            )
        return True

    def complete_client(self, client_id: str) -> bool:
        """
        Mark a client as completed (finished all planned activities).

        Completed clients no longer block barrier advancement. This allows
        clients with different simulation durations to coexist without deadlocks.

        Args:
            client_id: Unique identifier for the client

        Returns:
            bool: True if successfully marked as complete
        """
        if client_id in self.registered_clients:
            self._mark_client_as_completed(client_id)

            self.logger.info(
                "Client completed all activities",
                extra={
                    "extra_data": {
                        "client_id": client_id,
                        "remaining_active": len(self._get_active_clients()),
                        "total_completed": len(self.completed_clients),
                    }
                },
            )
            print(
                f"[Server] 🏁 Client {client_id} completed. "
                f"Active: {len(self._get_active_clients())}, "
                f"Completed: {len(self.completed_clients)}"
            )

            # Check if completing this client unblocks the barrier
            self._check_barrier_and_advance()
        return True

    def heartbeat(self, client_id: str) -> bool:
        """
        Record a heartbeat from a client to indicate it's still alive.

        Prevents the server from considering the client stale and removing it.

        Args:
            client_id: Unique identifier for the client

        Returns:
            bool: True if heartbeat recorded
        """
        if client_id in self.registered_clients:
            self.last_heartbeat[client_id] = time.time()
        return True

    def _get_active_clients(self) -> set:
        """
        Get the set of active clients (registered but not completed).

        Returns:
            set: Set of active client IDs
        """
        return self.registered_clients - self.completed_clients

    def _check_for_stale_clients(self):
        """
        Check for clients that haven't sent a heartbeat recently and remove them.

        This prevents deadlocks when clients crash or disconnect abruptly.
        """
        current_time = time.time()
        stale_clients = []

        for client_id in self._get_active_clients():
            # Use current time as default so newly registered clients aren't immediately stale
            # (register_client sets initial heartbeat timestamp)
            last_hb = self.last_heartbeat.get(client_id, current_time)
            if current_time - last_hb > self.timeout_seconds:
                stale_clients.append(client_id)

        for client_id in stale_clients:
            self.logger.warning(
                "Removing stale client (no heartbeat)",
                extra={
                    "extra_data": {
                        "client_id": client_id,
                        "timeout_seconds": self.timeout_seconds,
                        "last_heartbeat_ago": current_time - self.last_heartbeat.get(client_id, 0),
                    }
                },
            )
            print(
                f"[Server] ⚠️  Removing stale client {client_id} "
                f"(no heartbeat for {self.timeout_seconds}s)"
            )
            # Mark as completed to not block others
            self._mark_client_as_completed(client_id)

    def _mark_client_as_completed(self, client_id: str):
        """
        Mark a client as completed internally.

        Helper method to avoid code duplication between complete_client and stale detection.

        Args:
            client_id: Unique identifier for the client
        """
        self.completed_clients.add(client_id)
        self.submitted_clients.discard(client_id)

    def deregister_client(self, client_id: str) -> bool:
        """
        Remove a client from the server.

        Optional: Call this if a client shuts down gracefully.
        Otherwise, the server might hang waiting for a dead client.

        Args:
            client_id: Unique identifier for the client

        Returns:
            bool: True if deregistration successful
        """
        if client_id in self.registered_clients:
            self.registered_clients.remove(client_id)
            # Clean up all tracking data for this client
            self.submitted_clients.discard(client_id)
            self.completed_clients.discard(client_id)
            self.last_heartbeat.pop(client_id, None)

            self.logger.info(
                "Client deregistered",
                extra={
                    "extra_data": {
                        "client_id": client_id,
                        "remaining_clients": len(self.registered_clients),
                    }
                },
            )
            print(f"[Server] 🔴 Client {client_id} left. Total: {len(self.registered_clients)}")

            # Check if leaving unblocked the barrier
            self._check_barrier_and_advance()
        return True

    def get_instruction(self, client_id: str) -> SimulationInstruction:
        """
        Get the next simulation instruction for a client.

        Args:
            client_id: Unique identifier for the client

        Returns:
            SimulationInstruction: Instruction with status (WAIT/PROCEED) and simulation state
        """
        # Check for stale clients before processing
        self._check_for_stale_clients()

        # 1. Pause if not enough players
        active_clients = self._get_active_clients()
        if len(active_clients) < self.min_to_start:
            return SimulationInstruction(status="WAIT")

        # 2. Wait if this client already finished the current slot
        if client_id in self.submitted_clients:
            return SimulationInstruction(status="WAIT")

        # 3. Proceed
        return SimulationInstruction(
            status="PROCEED", day=self.day, slot=self.slot, recent_post_ids=self.recent_posts_cache
        )

    def submit_actions(self, client_id: str, actions: list) -> None:
        """
        Submit actions from a client for the current simulation slot.

        Args:
            client_id: Unique identifier for the client
            actions: List of ActionDTO objects representing agent actions
        """
        start_time = time.time()
        new_ids = []

        try:
            for act in actions:
                if act.action_type == "POST":
                    post_data = {
                        "agent_id": act.agent_id,
                        "cluster_id": act.cluster_id,
                        "content": act.content,
                        "day": self.day,
                        "slot": self.slot,
                    }
                    post_id = self.db.add_post(post_data)
                    if post_id:
                        new_ids.append(post_id)
                    else:
                        self.logger.warning(
                            f"Failed to add post for agent {act.agent_id}",
                            extra={"extra_data": {"agent_id": act.agent_id}},
                        )
                else:
                    interaction_data = {
                        "agent_id": act.agent_id,
                        "post_id": act.target_post_id,
                        "type": act.action_type,
                        "content": act.content,
                    }
                    self.db.add_interaction(interaction_data)

            if new_ids:
                self.recent_posts_cache.extend(new_ids)
                self.recent_posts_cache = self.recent_posts_cache[-50:]  # Keep last 50

            execution_time = (time.time() - start_time) * 1000

            self.logger.info(
                "Actions submitted",
                extra={
                    "extra_data": {
                        "client_id": client_id,
                        "day": self.day,
                        "slot": self.slot,
                        "num_actions": len(actions),
                        "num_posts": len(new_ids),
                        "execution_time_ms": execution_time,
                    }
                },
            )

        except Exception as e:
            self.logger.error(
                f"DB Error during action submission: {e}",
                extra={"extra_data": {"client_id": client_id, "error": str(e)}},
            )
            print(f"DB Error: {e}")

        # Mark this specific client as done
        self.submitted_clients.add(client_id)

        # Check if EVERYONE is done
        self._check_barrier_and_advance()

    def _check_barrier_and_advance(self) -> None:
        """
        Check if all active clients have submitted actions and advance simulation state.

        This implements the core dynamic barrier synchronization mechanism.
        Only waits for active clients (not completed ones).
        """
        active_clients = self._get_active_clients()
        active_count = len(active_clients)

        # Do not advance if no one is active
        if active_count == 0:
            return

        # Count how many active clients have submitted
        submitted_active_clients = self.submitted_clients & active_clients
        active_submitted_count = len(submitted_active_clients)

        # If all active clients have submitted, advance.
        if active_submitted_count >= active_count:
            execution_start = time.time()

            print(
                f"[Server] ✅ Day {self.day} Slot {self.slot} complete "
                f"(Active clients: {active_count}). Advancing..."
            )

            self.submitted_clients.clear()
            self.slot += 1

            # Check if day is complete and consolidate Redis data if needed
            day_completed = False
            if self.slot > 24:
                day_completed = True
                completed_day = self.day
                self.slot = 1
                self.day += 1

                # Consolidate Redis data to SQLite at end of day
                consolidation_result = self.db.consolidate_redis_to_sqlite(completed_day)
                if (
                    consolidation_result.get("posts", 0) > 0
                    or consolidation_result.get("interactions", 0) > 0
                    or consolidation_result.get("removed_posts", 0) > 0
                ):
                    self.logger.info(
                        f"Day {completed_day} complete - data consolidated to SQLite",
                        extra={
                            "extra_data": {
                                "completed_day": completed_day,
                                "posts_consolidated": consolidation_result.get("posts", 0),
                                "interactions_consolidated": consolidation_result.get(
                                    "interactions", 0
                                ),
                                "posts_removed_from_redis": consolidation_result.get(
                                    "removed_posts", 0
                                ),
                                "interactions_removed_from_redis": consolidation_result.get(
                                    "removed_interactions", 0
                                ),
                            }
                        },
                    )
                    print(
                        f"[Server] 💾 Day {completed_day} complete - "
                        f"Consolidated {consolidation_result.get('posts', 0)} posts, "
                        f"{consolidation_result.get('interactions', 0)} interactions to SQLite. "
                        f"Removed {consolidation_result.get('removed_posts', 0)} old posts, "
                        f"{consolidation_result.get('removed_interactions', 0)} old interactions from Redis"
                    )

            execution_time = (time.time() - execution_start) * 1000

            self.logger.info(
                "Simulation advanced",
                extra={
                    "extra_data": {
                        "new_day": self.day,
                        "new_slot": self.slot,
                        "num_active_clients": active_count,
                        "day_completed": day_completed,
                        "execution_time_ms": execution_time,
                    }
                },
            )
