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
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from classes.models import ActionDTO, AgentProfile, SimulationInstruction


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
        db_name: str,
        min_to_start: int = 1,
        config_path: str = ".",
        server_name: str = "orchestrator",
    ):
        """
        Initialize the orchestrator server.

        Args:
            db_name: Path to SQLite database file
            min_to_start: Minimum number of clients before simulation starts
            config_path: Path to configuration directory for logs
            server_name: Name of this server instance
        """
        from classes.models import Base

        # Initialize database
        self.engine = create_engine(f"sqlite:///{db_name}")
        Base.metadata.create_all(self.engine)

        # Server configuration
        self.min_to_start = min_to_start
        self.server_name = server_name
        self.config_path = Path(config_path)

        # Client tracking
        self.registered_clients = set()
        self.submitted_clients = set()
        self.registered_agents = {}  # {agent_id: username}

        # Simulation state
        self.day = 1
        self.slot = 1
        self.recent_posts_cache = []

        # Set up logging
        self._setup_logging()
        self.logger.info(
            "Orchestrator server initialized",
            extra={"extra_data": {"db_name": db_name, "min_to_start": min_to_start}},
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
        from classes.models import User_mgmt

        start_time = time.time()
        session = Session(self.engine)
        registered_count = 0
        skipped_count = 0

        try:
            for agent_profile in agents:
                # Check if agent already exists
                existing = session.query(User_mgmt).filter_by(id=agent_profile.id).first()

                if existing:
                    skipped_count += 1
                    self.registered_agents[agent_profile.id] = agent_profile.username
                    continue

                # Set joined_on if not set
                joined_on = agent_profile.joined_on
                if joined_on == 0:
                    joined_on = int(time.time())

                # Create new user record
                user = User_mgmt(
                    id=agent_profile.id,
                    username=agent_profile.username,
                    email=agent_profile.email,
                    password=agent_profile.password,
                    leaning=agent_profile.leaning,
                    user_type=agent_profile.user_type,
                    age=agent_profile.age,
                    oe=agent_profile.oe,
                    co=agent_profile.co,
                    ex=agent_profile.ex,
                    ag=agent_profile.ag,
                    ne=agent_profile.ne,
                    recsys_type=agent_profile.recsys_type,
                    frecsys_type=agent_profile.frecsys_type,
                    language=agent_profile.language,
                    owner=agent_profile.owner,
                    education_level=agent_profile.education_level,
                    joined_on=joined_on,
                    gender=agent_profile.gender,
                    nationality=agent_profile.nationality,
                    round_actions=agent_profile.round_actions,
                    toxicity=agent_profile.toxicity,
                    is_page=agent_profile.is_page,
                    left_on=agent_profile.left_on,
                    daily_activity_level=agent_profile.daily_activity_level,
                    profession=agent_profile.profession,
                    activity_profile=agent_profile.activity_profile,
                    archetype=agent_profile.archetype,
                )
                session.add(user)
                registered_count += 1
                self.registered_agents[agent_profile.id] = agent_profile.username

            session.commit()
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
            session.rollback()
            self.logger.error(
                f"Agent registration error: {e}", extra={"extra_data": {"error": str(e)}}
            )
            print(f"[Server] ❌ Agent registration error: {e}")
            raise
        finally:
            session.close()

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
            execution_time = (time.time() - start_time) * 1000

            self.logger.info(
                "Client registered",
                extra={
                    "extra_data": {
                        "client_id": client_id,
                        "total_clients": len(self.registered_clients),
                        "execution_time_ms": execution_time,
                    }
                },
            )
            print(f"[Server] 🟢 Client {client_id} joined. Total: {len(self.registered_clients)}")
        return True

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
            # If we were waiting ONLY for this client, we might be able to advance now
            self.submitted_clients.discard(client_id)

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
        # 1. Pause if not enough players
        if len(self.registered_clients) < self.min_to_start:
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
        from classes.models import InteractionModel, PostModel

        session = Session(self.engine)
        new_ids = []

        try:
            for act in actions:
                if act.action_type == "POST":
                    p = PostModel(
                        agent_id=act.agent_id,
                        cluster_id=act.cluster_id,
                        content=act.content,
                        day=self.day,
                        slot=self.slot,
                    )
                    session.add(p)
                    session.flush()
                    new_ids.append(p.id)
                else:
                    session.add(
                        InteractionModel(
                            agent_id=act.agent_id,
                            post_id=act.target_post_id,
                            type=act.action_type,
                            content=act.content,
                        )
                    )

            session.commit()

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
        finally:
            session.close()

        # Mark this specific client as done
        self.submitted_clients.add(client_id)

        # Check if EVERYONE is done
        self._check_barrier_and_advance()

    def _check_barrier_and_advance(self) -> None:
        """
        Check if all clients have submitted actions and advance simulation state.

        This implements the core dynamic barrier synchronization mechanism.
        """
        current_count = len(self.registered_clients)

        # Do not advance if no one is connected
        if current_count == 0:
            return

        # If everyone who is CURRENTLY registered has submitted, advance.
        if len(self.submitted_clients) >= current_count:
            execution_start = time.time()

            print(
                f"[Server] ✅ Day {self.day} Slot {self.slot} complete (Agents: {current_count}). Advancing..."
            )

            self.submitted_clients.clear()
            self.slot += 1

            if self.slot > 24:
                self.slot = 1
                self.day += 1

            execution_time = (time.time() - execution_start) * 1000

            self.logger.info(
                "Simulation advanced",
                extra={
                    "extra_data": {
                        "new_day": self.day,
                        "new_slot": self.slot,
                        "num_clients": current_count,
                        "execution_time_ms": execution_time,
                    }
                },
            )
