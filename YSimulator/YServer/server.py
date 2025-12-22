"""
YServer - Orchestrator Server for YSimulator.

This module contains the Ray remote actor that orchestrates the simulation,
managing client registration, agent actions, and simulation state progression.
"""

import json
import logging
import random
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import ray
from sqlalchemy import text

from YSimulator.YClient.classes.ray_models import SimulationInstruction


# Constants
RECOMMENDATION_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days in seconds
NETWORK_EDGE_CHECK_LIMIT = 10  # Number of edges to check when verifying network load


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
        simulation_config: dict = None,
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
            simulation_config: Simulation configuration dict (optional)
        """
        from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware

        # Server configuration
        self.min_to_start = min_to_start
        self.server_name = server_name
        self.config_path = Path(config_path)
        self.timeout_seconds = timeout_seconds

        # Archetype configuration
        if simulation_config is None:
            simulation_config = {}
        self.archetype_config = simulation_config.get("agent_archetypes", {})
        self.archetypes_enabled = self.archetype_config.get("enabled", False)
        self.archetype_distribution = self.archetype_config.get("distribution", {})
        self.archetype_transitions = self.archetype_config.get("transitions", {})
        
        # Track last archetype transition day (start at 0, so first transition at day 7)
        self.last_archetype_transition_day = 0
        
        # Simulation timing configuration
        self.num_slots_per_day = simulation_config.get("simulation", {}).get("num_slots_per_day", 24)

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
        self.current_round_id = None  # Will be set when simulation starts

        # Set up logging first
        self._setup_logging()

        # Initialize database middleware
        self.db = DatabaseMiddleware(
            db_config=db_config,
            config_path=str(self.config_path),
            redis_config=redis_config,
            logger=self.logger,
        )
        
        # Initialize the first round entry
        self.current_round_id = self.db.get_or_create_round(self.day, self.slot)

        self.logger.info(
            "Orchestrator server initialized",
            extra={
                "extra_data": {
                    "db_type": db_config.get("type", "sqlite"),
                    "min_to_start": min_to_start,
                    "redis_enabled": self.db.use_redis,
                    "timeout_seconds": timeout_seconds,
                    "archetypes_enabled": self.archetypes_enabled,
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
        For page agents (is_page=1), also creates a Website entry.

        Args:
            agents: List of AgentProfile dataclass instances

        Returns:
            dict: Summary of registration results with counts
        """
        start_time = time.time()
        registered_count = 0
        skipped_count = 0
        pages_registered = 0

        try:
            for agent_profile in agents:
                # Prepare user data
                user_data = {
                    "id": str(agent_profile.id),  # Convert to UUID string
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
                    "joined_on": self.current_round_id,  # FK to rounds table (UUID string)
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
                user_registered = self.db.register_user(user_data)
                if user_registered:
                    registered_count += 1
                    self.registered_agents[agent_profile.id] = agent_profile.username
                    
                    # If this is a page agent, create a Website entry
                    if agent_profile.is_page == 1 and agent_profile.feed_url:
                        website_data = {
                            "id": str(agent_profile.id),  # Website ID = User ID
                            "name": agent_profile.username,  # Use username as website name
                            "rss": agent_profile.feed_url,
                            "category": "page",  # Mark as page
                            "language": agent_profile.language,
                            "country": agent_profile.nationality,
                            "leaning": agent_profile.leaning,
                        }
                        if self.db.add_website(website_data):
                            pages_registered += 1
                        else:
                            self.logger.warning(
                                f"Failed to create website for page {agent_profile.username}",
                                extra={"extra_data": {"page_id": str(agent_profile.id)}}
                            )
                else:
                    skipped_count += 1
                    self.registered_agents[agent_profile.id] = agent_profile.username
                    
                    # If page already exists, ensure its Website entry also exists
                    if agent_profile.is_page == 1 and agent_profile.feed_url:
                        # Check if website exists
                        website_data = self.db.get_website_by_rss(agent_profile.feed_url)
                        if website_data:
                            pages_registered += 1
                        else:
                            # Website doesn't exist, create it now
                            self.logger.info(
                                f"Creating missing website for existing page {agent_profile.username}",
                                extra={"extra_data": {"page_id": str(agent_profile.id)}}
                            )
                            website_data = {
                                "id": str(agent_profile.id),  # Website ID = User ID
                                "name": agent_profile.username,  # Use username as website name
                                "rss": agent_profile.feed_url,
                                "category": "page",  # Mark as page
                                "language": agent_profile.language,
                                "country": agent_profile.nationality,
                                "leaning": agent_profile.leaning,
                            }
                            if self.db.add_website(website_data):
                                pages_registered += 1
                            else:
                                self.logger.warning(
                                    f"Failed to create website for existing page {agent_profile.username}",
                                    extra={"extra_data": {"page_id": str(agent_profile.id)}}
                                )

            execution_time = (time.time() - start_time) * 1000

            self.logger.info(
                "Agent registration complete",
                extra={
                    "extra_data": {
                        "registered": registered_count,
                        "skipped": skipped_count,
                        "pages": pages_registered,
                        "total": len(self.registered_agents),
                        "execution_time_ms": execution_time,
                    }
                },
            )

            print(
                f"[Server] 👥 Agent Registration: {registered_count} new, {skipped_count} existing, {pages_registered} pages"
            )

            return {
                "registered": registered_count,
                "skipped": skipped_count,
                "pages": pages_registered,
                "total": len(self.registered_agents),
            }

        except Exception as e:
            self.logger.error(
                f"Agent registration error: {e}", extra={"extra_data": {"error": str(e)}}
            )
            print(f"[Server] ❌ Agent registration error: {e}")
            raise

    def add_follow_relationship(self, follow_data: dict) -> bool:
        """
        Add a follow relationship to the database.
        
        This method is called by clients to create follow relationships,
        typically during initial social network setup from network.csv.
        
        Args:
            follow_data: Dictionary containing:
                - user_id: UUID of user being followed
                - follower_id: UUID of follower
                - action: 'follow' or 'unfollow'
                - round: Round ID (can be empty for initial setup)
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            success = self.db.add_follow(follow_data)
            return success
        except Exception as e:
            self.logger.error(
                f"Error adding follow relationship: {e}",
                extra={"extra_data": {"error": str(e), "follow_data": follow_data}}
            )
            return False

    def check_network_edges_exist(self, edges: list) -> bool:
        """
        Check if any of the network edges already exist in the Follow table.
        
        This method checks if the social network from network.csv has already been loaded
        by verifying if any of the specified edges exist in the database.
        
        Args:
            edges: List of tuples (follower_id, user_id) representing network edges
        
        Returns:
            bool: True if any edge exists, False if none exist
        """
        if not edges:
            return False
        
        try:
            from sqlalchemy.orm import Session
            from YSimulator.YServer.classes.models import Follow
            
            with Session(self.db.engine) as session:
                # Check if any of the edges exist
                # We only need to find one to know the network was loaded
                for follower_id, user_id in edges[:NETWORK_EDGE_CHECK_LIMIT]:
                    exists = session.query(Follow).filter_by(
                        follower_id=follower_id,
                        user_id=user_id,
                        action="follow"
                    ).first()
                    
                    if exists:
                        self.logger.info(
                            f"Network already loaded (found edge: {follower_id} -> {user_id})"
                        )
                        return True
                
                # None of the checked edges exist
                self.logger.info("Network not yet loaded (no edges found in database)")
                return False
                
        except Exception as e:
            self.logger.error(
                f"Error checking network edges: {e}",
                extra={"extra_data": {"error": str(e)}}
            )
            # On error, assume network not loaded to be safe
            return False

    def get_first_round_id(self) -> str:
        """
        Get the UUID of the first round (day 1, slot 1).
        
        This method retrieves or creates the first round entry in the database,
        which is used as the Round reference for initial network edges loaded
        from network.csv.
        
        Returns:
            str: UUID of the first round (day 1, slot 1)
        """
        try:
            # Get or create the first round (day 1, slot 1)
            first_round_id = self.db.get_or_create_round(1, 1)
            self.logger.info(f"Retrieved first round ID: {first_round_id}")
            return first_round_id
        except Exception as e:
            self.logger.error(
                f"Error getting first round ID: {e}",
                extra={"extra_data": {"error": str(e)}}
            )
            # Return empty string as fallback (better than crashing)
            return ""

    def check_follow_relationship(self, follower_id: str, user_id: str) -> bool:
        """
        Check if a follow relationship exists between two users.
        
        Args:
            follower_id: UUID of the follower
            user_id: UUID of the user being followed
        
        Returns:
            bool: True if follower follows user with action="follow", False otherwise
        """
        try:
            from sqlalchemy.orm import Session
            from YSimulator.YServer.classes.models import Follow
            
            with Session(self.db.engine) as session:
                # Check for active follow relationship
                # Get the most recent follow action between these users
                latest_follow = session.query(Follow).filter_by(
                    follower_id=follower_id,
                    user_id=user_id
                ).order_by(Follow.round.desc()).first()
                
                # Return True if latest action is "follow", False otherwise
                return latest_follow and latest_follow.action == "follow"
                
        except Exception as e:
            self.logger.error(
                f"Error checking follow relationship: {e}",
                extra={"extra_data": {"error": str(e), "follower_id": follower_id, "user_id": user_id}}
            )
            return False

    def register_client(self, client_id: str, num_days: int = 0) -> dict:
        """
        Register a new client with the server.

        Provides the current server state (day and slot) as the starting point.
        The client will handle its own simulation step counting from this point.

        Args:
            client_id: Unique identifier for the client
            num_days: Number of days this client plans to simulate (informational only)

        Returns:
            dict: {"registered": bool, "start_day": int, "start_slot": int}
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
                        "start_day": self.day,
                        "start_slot": self.slot,
                        "num_days": num_days,
                        "total_clients": len(self.registered_clients),
                        "active_clients": len(self._get_active_clients()),
                        "execution_time_ms": execution_time,
                    }
                },
            )
            print(
                f"[Server] 🟢 Client {client_id} joined at day {self.day}, slot {self.slot}. "
                f"Will run for {num_days if num_days > 0 else '∞'} days. "
                f"Total: {len(self.registered_clients)}, Active: {len(self._get_active_clients())}"
            )
        
        # Return current server state as starting point for client
        return {
            "registered": True,
            "start_day": self.day,
            "start_slot": self.slot,
        }

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

        Heartbeat-based liveness: Clients are only considered stale if they stop
        sending heartbeats. Processing time doesn't matter - if heartbeats arrive,
        the client is alive. This prevents false positives on slow/busy clients.
        """
        current_time = time.time()
        stale_clients = []
        stale_clients_info = {}  # Store time_since_heartbeat for each stale client

        for client_id in self._get_active_clients():
            # Check if heartbeat was ever received (should be set during registration)
            if client_id not in self.last_heartbeat:
                # This shouldn't happen, but log and skip to avoid crashes
                self.logger.warning(
                    f"Active client {client_id} has no heartbeat entry, initializing",
                    extra={"extra_data": {"client_id": client_id}}
                )
                self.last_heartbeat[client_id] = current_time
                continue
                
            last_hb = self.last_heartbeat[client_id]
            time_since_heartbeat = current_time - last_hb
            
            # Only mark as stale if no heartbeat received within timeout
            # Note: Clients send heartbeat every heartbeat_interval seconds,
            # so timeout_seconds should be >> heartbeat_interval to account for
            # network delays and processing variations
            if time_since_heartbeat > self.timeout_seconds:
                stale_clients.append(client_id)
                stale_clients_info[client_id] = time_since_heartbeat

        for client_id in stale_clients:
            time_since_heartbeat = stale_clients_info[client_id]
            self.logger.warning(
                "Removing stale client (no heartbeat)",
                extra={
                    "extra_data": {
                        "client_id": client_id,
                        "timeout_seconds": self.timeout_seconds,
                        "last_heartbeat_ago": time_since_heartbeat,
                    }
                },
            )
            print(
                f"[Server] ⚠️  Removing stale client {client_id} "
                f"(no heartbeat for {time_since_heartbeat:.1f}s)"
            )
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

        The server provides the current day/slot. The client is responsible for
        tracking its own progress and deciding when to stop based on its start point
        and configured duration.

        Args:
            client_id: Unique identifier for the client

        Returns:
            SimulationInstruction: Instruction with status (WAIT/PROCEED) and current simulation state
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

        # 3. Proceed with current server state
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
                        "user_id": str(act.agent_id),  # FK to user_mgmt.id (UUID string)
                        "tweet": act.content,  # Post content field
                        "round": self.current_round_id,  # FK to rounds.id
                    }
                    # Add article_id (news_id) if this is a news post
                    if hasattr(act, 'article_id') and act.article_id:
                        post_data["news_id"] = act.article_id
                    
                    post_id = self.db.add_post(post_data)
                    if post_id:
                        new_ids.append(post_id)
                    else:
                        self.logger.warning(
                            f"Failed to add post for agent {act.agent_id}",
                            extra={"extra_data": {"agent_id": act.agent_id}},
                        )
                
                elif act.action_type == "COMMENT":
                    # Comments are stored as posts with comment_to set
                    # Get the parent post to inherit thread_id (which points to the root of the thread)
                    parent_post = self.db.get_post(act.target_post_id)
                    if parent_post:
                        # Get thread_id from parent - this will point to the root post
                        # because:
                        # 1. If parent is a root post, thread_id equals parent's ID
                        # 2. If parent is a comment, it already inherited root's thread_id
                        # So we recursively inherit the correct root thread_id
                        thread_id = parent_post.get("thread_id")
                        
                        # Fallback: If parent doesn't have thread_id (legacy data), 
                        # assume parent IS the root post
                        if not thread_id:
                            thread_id = act.target_post_id
                        
                        post_data = {
                            "user_id": str(act.agent_id),
                            "tweet": act.content,
                            "round": self.current_round_id,
                            "comment_to": act.target_post_id,  # Points to immediate parent
                            "thread_id": thread_id,  # Points to root post of thread
                        }
                        post_id = self.db.add_post(post_data)
                        if post_id:
                            new_ids.append(post_id)
                        else:
                            self.logger.warning(
                                f"Failed to add comment for agent {act.agent_id}",
                                extra={"extra_data": {"agent_id": act.agent_id}},
                            )
                    else:
                        self.logger.warning(
                            f"Parent post not found for comment: {act.target_post_id}",
                            extra={"extra_data": {"agent_id": act.agent_id, "target_post_id": act.target_post_id}},
                        )
                
                elif act.action_type == "SHARE":
                    # Share action: create a new post referencing the original
                    # Get the original post to copy news_id if present
                    original_post = self.db.get_post(act.target_post_id)
                    if original_post:
                        post_data = {
                            "user_id": str(act.agent_id),
                            "tweet": act.content if act.content else "",  # Optional commentary
                            "round": self.current_round_id,
                            "shared_from": act.target_post_id,
                        }
                        # If the original post references an article, copy the reference
                        # Use helper method for consistent empty/default value checking
                        news_id = original_post.get("news_id")
                        if not self.db._is_empty_or_default(news_id):
                            post_data["news_id"] = news_id
                        
                        post_id = self.db.add_post(post_data)
                        if post_id:
                            new_ids.append(post_id)
                        else:
                            self.logger.warning(
                                f"Failed to add share for agent {act.agent_id}",
                                extra={"extra_data": {"agent_id": act.agent_id}},
                            )
                    else:
                        self.logger.warning(
                            f"Original post not found for share: {act.target_post_id}",
                            extra={"extra_data": {"agent_id": act.agent_id, "target_post_id": act.target_post_id}},
                        )
                
                elif act.action_type == "FOLLOW":
                    # Follow action: create follow relationship
                    follow_data = {
                        "follower_id": str(act.agent_id),  # FK to user_mgmt.id (UUID string) - agent who is following
                        "user_id": act.target_user_id,  # FK to user_mgmt.id (UUID string) - user being followed
                        "action": "follow",
                        "round": self.current_round_id,  # FK to rounds.id
                    }
                    success = self.db.add_follow(follow_data)
                    if not success:
                        self.logger.warning(
                            f"Failed to add follow for agent {act.agent_id}",
                            extra={"extra_data": {"agent_id": act.agent_id, "target_user_id": act.target_user_id}},
                        )
                
                elif act.action_type == "UNFOLLOW":
                    # Unfollow action: create unfollow relationship record
                    unfollow_data = {
                        "follower_id": str(act.agent_id),  # FK to user_mgmt.id (UUID string) - agent who is unfollowing
                        "user_id": act.target_user_id,  # FK to user_mgmt.id (UUID string) - user being unfollowed
                        "action": "unfollow",
                        "round": self.current_round_id,  # FK to rounds.id
                    }
                    success = self.db.add_follow(unfollow_data)
                    if not success:
                        self.logger.warning(
                            f"Failed to add unfollow for agent {act.agent_id}",
                            extra={"extra_data": {"agent_id": act.agent_id, "target_user_id": act.target_user_id}},
                        )
                
                else:
                    # Other interactions (LIKE, etc.)
                    interaction_data = {
                        "user_id": str(act.agent_id),  # FK to user_mgmt.id (UUID string)
                        "post_id": act.target_post_id,  # FK to post.id (UUID string)
                        "type": act.action_type,  # Field name is 'type' not 'reaction_type'
                        "round": self.current_round_id,  # FK to rounds.id
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

    def add_website(self, website_data: dict) -> Optional[str]:
        """
        Add a website (news source) to the database.
        
        This is a wrapper method that can be called remotely from Ray actors.
        
        Args:
            website_data: Dictionary containing website information
            
        Returns:
            str: Website ID if successful, None otherwise
        """
        return self.db.add_website(website_data)
    
    def get_website_by_rss(self, rss_url: str) -> Optional[dict]:
        """
        Get website information by RSS URL.
        
        This is a wrapper method that can be called remotely from Ray actors.
        
        Args:
            rss_url: RSS feed URL
            
        Returns:
            dict: Website information if found, None otherwise
        """
        return self.db.get_website_by_rss(rss_url)
    
    def add_article(self, article_data: dict) -> Optional[str]:
        """
        Add a news article to the database.
        
        This is a wrapper method that can be called remotely from Ray actors.
        
        Args:
            article_data: Dictionary containing article information
            
        Returns:
            str: Article ID if successful, None otherwise
        """
        return self.db.add_article(article_data)

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
                
                # Check if it's time for archetype transitions (every 7 days)
                if self.archetypes_enabled and self.day - self.last_archetype_transition_day >= 7:
                    self._perform_archetype_transitions()
                    self.last_archetype_transition_day = self.day

            # Update Round table with new time
            self.current_round_id = self.db.get_or_create_round(self.day, self.slot)

            execution_time = (time.time() - execution_start) * 1000

            self.logger.info(
                "Simulation advanced",
                extra={
                    "extra_data": {
                        "new_day": self.day,
                        "new_slot": self.slot,
                        "round_id": self.current_round_id,
                        "num_active_clients": active_count,
                        "day_completed": day_completed,
                        "execution_time_ms": execution_time,
                    }
                },
            )

    def _perform_archetype_transitions(self) -> None:
        """
        Perform archetype transitions for all registered agents based on transition probabilities.
        
        Each agent has a probability of transitioning to a different archetype based on their
        current archetype and the transition matrix defined in the configuration.
        This is called every 7 days when archetypes are enabled.
        """
        import random
        
        # Tolerance for probability sum validation
        PROBABILITY_TOLERANCE = 0.01
        
        if not self.archetypes_enabled or not self.archetype_transitions:
            return
        
        transition_start = time.time()
        transitioned_count = 0
        error_count = 0
        
        # Get all registered agents from database
        try:
            # Query all users and their current archetypes
            agents = self.db.get_all_users()
            
            for agent in agents:
                agent_id = agent.get("id")
                current_archetype = agent.get("archetype")
                
                # Skip if agent has no archetype
                if not current_archetype:
                    continue
                
                # Normalize archetype to lowercase for comparison
                current_archetype_lower = current_archetype.lower()
                
                # Skip if archetype not in transitions
                if current_archetype_lower not in self.archetype_transitions:
                    continue
                
                # Get transition probabilities for current archetype
                transitions = self.archetype_transitions.get(current_archetype_lower, {})
                
                if not transitions:
                    continue
                
                # Sample new archetype based on transition probabilities
                archetypes = list(transitions.keys())
                probabilities = list(transitions.values())
                
                # Validate probabilities sum to approximately 1.0
                total_prob = sum(probabilities)
                if abs(total_prob - 1.0) > PROBABILITY_TOLERANCE:
                    self.logger.warning(
                        f"Archetype transition probabilities for '{current_archetype}' sum to {total_prob}, expected 1.0"
                    )
                    # Normalize probabilities
                    probabilities = [p / total_prob for p in probabilities]
                
                # Select new archetype using weighted random choice
                new_archetype = random.choices(archetypes, weights=probabilities)[0]
                
                # Update agent archetype in database if it changed
                if new_archetype != current_archetype_lower:
                    # Capitalize first letter to match format
                    new_archetype_formatted = new_archetype.capitalize()
                    
                    if self.db.update_user_archetype(agent_id, new_archetype_formatted):
                        transitioned_count += 1
                        self.logger.debug(
                            f"Agent {agent_id} transitioned from {current_archetype} to {new_archetype_formatted}"
                        )
                    else:
                        error_count += 1
        
        except Exception as e:
            self.logger.error(
                f"Error during archetype transitions: {e}",
                extra={"extra_data": {"error": str(e)}}
            )
            print(f"[Server] ❌ Archetype transition error: {e}")
            return
        
        transition_time = (time.time() - transition_start) * 1000
        
        self.logger.info(
            f"Archetype transitions complete at day {self.day}",
            extra={
                "extra_data": {
                    "day": self.day,
                    "transitioned_count": transitioned_count,
                    "error_count": error_count,
                    "total_agents": len(agents),
                    "execution_time_ms": transition_time,
                }
            },
        )
        
        print(
            f"[Server] 🔄 Archetype transitions complete - "
            f"{transitioned_count} agents changed archetypes (day {self.day})"
        )
    
    def _calculate_visibility_params(self, visibility_rounds: int) -> tuple:
        """
        Calculate visibility day/hour parameters for filtering posts.
        
        Since Round IDs are UUIDs (not sequential integers), we calculate
        the day/hour threshold instead of trying to do arithmetic on UUIDs.
        
        Args:
            visibility_rounds: Number of time slots to look back
            
        Returns:
            tuple: (visibility_day, visibility_hour) representing the oldest round to show
        """
        # Use num_slots_per_day from config, with fallback to 24
        slots_per_day = getattr(self, 'num_slots_per_day', 24)
        
        total_hours = (self.day - 1) * slots_per_day + self.slot
        visibility_hours = max(1, total_hours - visibility_rounds)
        visibility_day = (visibility_hours - 1) // slots_per_day + 1
        visibility_hour = (visibility_hours - 1) % slots_per_day + 1
        return visibility_day, visibility_hour
    
    def _save_recommendation(self, agent_id: str, post_ids: List[str]) -> None:
        """
        Save recommendations to the database (and Redis if enabled).
        
        Stores the list of recommended posts for an agent in the current round,
        formatted as a pipe-separated string (e.g., "post_id1|post_id2|post_id3").
        
        Args:
            agent_id: UUID of the agent receiving recommendations
            post_ids: List of post UUIDs recommended to the agent
        """
        if not post_ids:
            return
        
        try:
            # Format post IDs as pipe-separated string (original implementation format)
            post_ids_str = "|".join(post_ids)
            recommendation_id = str(uuid.uuid4())
            
            # Save to SQL database
            with self.db.engine.begin() as connection:
                query = text("""
                    INSERT INTO recommendations (id, user_id, post_ids, round)
                    VALUES (:id, :user_id, :post_ids, :round)
                """)
                connection.execute(query, {
                    "id": recommendation_id,
                    "user_id": agent_id,
                    "post_ids": post_ids_str,
                    "round": self.current_round_id
                })
            
            # Also save to Redis if enabled
            if self.db.use_redis:
                # Store recommendation in Redis with key format: ysim:recommendations:{user_id}:{round_id}
                rec_key = self.db._redis_key("recommendations", f"{agent_id}:{self.current_round_id}")
                self.db.redis_client.set(rec_key, post_ids_str)
                # Set TTL to prevent unbounded growth
                self.db.redis_client.expire(rec_key, RECOMMENDATION_TTL_SECONDS)
                
            self.logger.debug(
                f"Saved recommendation for agent {agent_id}: {len(post_ids)} posts",
                extra={
                    "extra_data": {
                        "agent_id": agent_id,
                        "round": self.current_round_id,
                        "post_count": len(post_ids)
                    }
                }
            )
            
        except Exception as e:
            self.logger.error(
                f"Error saving recommendation: {e}",
                extra={"extra_data": {"agent_id": agent_id, "error": str(e)}}
            )
    
    def get_recommended_posts(
        self,
        agent_id: str,
        mode: str = "random",
        limit: int = 5,
        visibility_rounds: int = 36,
        followers_ratio: float = 0.6
    ) -> List[str]:
        """
        Get recommended posts for an agent using the specified recommendation strategy.
        
        Args:
            agent_id: UUID of the agent requesting recommendations
            mode: Recommendation mode:
                - "random": Random post ordering (default)
                - "rchrono": Reverse chronological ordering (newest first)
                - "rchrono_popularity": Reverse chronological with popularity boost
                - "rchrono_followers": Prioritizes posts from followed users
                - "rchrono_followers_popularity": Followers + popularity
                - "rchrono_comments": Prioritizes highly commented posts
                - "common_interests": Posts with common topic interests
                - "common_user_interests": Posts by users with common interests
                - "similar_users_react": Posts from similar users (by reactions)
                - "similar_users_posts": Posts from similar users (by posting)
            limit: Number of posts to recommend (default: 5)
            visibility_rounds: Number of rounds (time slots) to look back for posts (default: 36)
            followers_ratio: Ratio of posts from followers vs others (default: 0.6)
            
        Returns:
            List[str]: List of post UUIDs recommended for the agent
        """
        try:
            # Calculate visibility threshold based on day/hour (not UUID arithmetic)
            visibility_day, visibility_hour = self._calculate_visibility_params(visibility_rounds)
            
            if self.db.use_redis:
                # Use Redis for recommendations
                # Note: Redis has limited support for complex queries
                # For modes requiring joins (followers, topics, etc.), we fallback to simpler modes
                
                # Get recent posts from Redis
                recent_posts_key = self.db._redis_key("posts", "recent")
                all_post_ids = self.db.redis_client.lrange(recent_posts_key, 0, -1)
                
                # Use Redis pipeline to fetch post data efficiently (avoid N+1 queries)
                if all_post_ids:
                    pipeline = self.db.redis_client.pipeline()
                    for post_id in all_post_ids:
                        post_key = self.db._redis_key("posts", post_id)
                        pipeline.hgetall(post_key)
                    
                    # Execute pipeline and get all results at once
                    posts_data = pipeline.execute()
                    
                    # Build list of valid posts with metadata
                    # For Redis, we don't filter by round visibility (UUID comparison issue)
                    # The recent list is already limited to last 50 posts
                    valid_posts_with_data = []
                    for i, post_data in enumerate(posts_data):
                        if post_data:
                            post_user_id = post_data.get("user_id")
                            # Exclude own posts
                            if post_user_id and post_user_id != agent_id:
                                valid_posts_with_data.append({
                                    'id': all_post_ids[i],
                                    'index': i,  # Preserve chronological order (lower index = newer)
                                    'reaction_count': int(post_data.get("reaction_count", 0) or 0)
                                })
                else:
                    valid_posts_with_data = []
                
                # Apply mode-specific ordering
                if mode == "rchrono":
                    # Redis recent list is already in reverse chronological order (newest first)
                    # Just take the first 'limit' items
                    post_ids = [p['id'] for p in valid_posts_with_data[:limit]]
                    
                elif mode == "rchrono_popularity":
                    # Sort by index (time proxy) first, then by reaction_count
                    # This aligns better with SQL which sorts by time first, then popularity
                    sorted_posts = sorted(valid_posts_with_data, 
                                        key=lambda x: (x['index'], -x['reaction_count']))
                    post_ids = [p['id'] for p in sorted_posts[:limit]]
                    
                elif mode == "rchrono_followers":
                    # Filter posts from followed users using hybrid SQL+Redis
                    follower_posts_limit = int(limit * followers_ratio)
                    additional_posts_limit = limit - follower_posts_limit
                    
                    # Helper: Get followed user IDs (shared with rchrono_followers_popularity)
                    with self.db.engine.begin() as connection:
                        result = connection.execute(
                            text("SELECT follower_id FROM follow WHERE user_id = :agent_id AND action = 'follow'"),
                            {"agent_id": agent_id}
                        )
                        followed_user_ids = set(row[0] for row in result)
                    
                    # Create mapping for efficient lookup (avoid O(n²))
                    post_id_to_data = {all_post_ids[i]: posts_data[i] for i in range(len(all_post_ids))}
                    
                    # Filter posts by followed users
                    follower_posts = []
                    other_posts = []
                    for post in valid_posts_with_data:
                        post_data = post_id_to_data.get(post['id'])
                        if post_data and post_data.get('user_id') in followed_user_ids:
                            follower_posts.append(post)
                        else:
                            other_posts.append(post)
                    
                    # Take from followers first, then fill with others
                    post_ids = [p['id'] for p in follower_posts[:follower_posts_limit]]
                    if len(post_ids) < limit:
                        post_ids.extend([p['id'] for p in other_posts[:additional_posts_limit]])
                    
                elif mode == "rchrono_followers_popularity":
                    # Combine followers and popularity with hybrid approach
                    follower_posts_limit = int(limit * followers_ratio)
                    additional_posts_limit = limit - follower_posts_limit
                    
                    # Get follow relationships (same query as rchrono_followers)
                    with self.db.engine.begin() as connection:
                        result = connection.execute(
                            text("SELECT follower_id FROM follow WHERE user_id = :agent_id AND action = 'follow'"),
                            {"agent_id": agent_id}
                        )
                        followed_user_ids = set(row[0] for row in result)
                    
                    # Create mapping for efficient lookup
                    post_id_to_data = {all_post_ids[i]: posts_data[i] for i in range(len(all_post_ids))}
                    
                    # Filter and sort
                    follower_posts = []
                    other_posts = []
                    for post in valid_posts_with_data:
                        post_data = post_id_to_data.get(post['id'])
                        if post_data and post_data.get('user_id') in followed_user_ids:
                            follower_posts.append(post)
                        else:
                            other_posts.append(post)
                    
                    # Sort by index (time) then popularity
                    follower_posts_sorted = sorted(follower_posts, key=lambda x: (x['index'], -x['reaction_count']))
                    other_posts_sorted = sorted(other_posts, key=lambda x: (x['index'], -x['reaction_count']))
                    
                    post_ids = [p['id'] for p in follower_posts_sorted[:follower_posts_limit]]
                    if len(post_ids) < limit:
                        post_ids.extend([p['id'] for p in other_posts_sorted[:additional_posts_limit]])
                    
                elif mode == "rchrono_comments":
                    # Count comments for each post using Redis
                    # For each post, count how many posts have comment_to = this post_id
                    posts_with_comment_counts = []
                    for i, post_data in enumerate(posts_data):
                        if post_data and post_data.get('user_id') != agent_id:
                            post_id = all_post_ids[i]
                            # Check if this is a top-level post (not a comment itself)
                            if post_data.get('comment_to', '-1') == '-1':
                                # Count comments by checking other posts
                                comment_count = sum(1 for pd in posts_data if pd and pd.get('comment_to') == post_id)
                                posts_with_comment_counts.append({
                                    'id': post_id,
                                    'index': i,
                                    'comment_count': comment_count,
                                    'reaction_count': int(post_data.get("reaction_count", 0) or 0)
                                })
                    
                    # Sort by comment count desc, then by recency
                    sorted_posts = sorted(posts_with_comment_counts, 
                                        key=lambda x: (-x['comment_count'], x['index']))
                    post_ids = [p['id'] for p in sorted_posts[:limit]]
                    
                elif mode == "common_interests":
                    # Posts matching user's topic interests
                    # Assumes Redis will have: ysim:user:{user_id}:interests (set), ysim:post:{post_id}:topics (set)
                    # Note: Redis client uses decode_responses=True, so SMEMBERS returns strings
                    
                    # Try to get user interests from Redis (future: will be cached)
                    user_interests_key = self.db._redis_key("user", agent_id) + ":interests"
                    if self.db.redis_client.exists(user_interests_key):
                        # Redis implementation when data is available
                        user_interests = self.db.redis_client.smembers(user_interests_key)
                        
                        # Create mapping for efficient lookup
                        post_id_to_data = {all_post_ids[i]: posts_data[i] for i in range(len(all_post_ids))}
                        
                        # Score posts by number of matching interests
                        posts_with_scores = []
                        for post in valid_posts_with_data:
                            post_topics_key = self.db._redis_key("post", post['id']) + ":topics"
                            if self.db.redis_client.exists(post_topics_key):
                                post_topics = self.db.redis_client.smembers(post_topics_key)
                                # Calculate intersection (common interests)
                                common_count = len(user_interests & post_topics)
                                if common_count > 0:
                                    posts_with_scores.append({
                                        'id': post['id'],
                                        'index': post['index'],
                                        'score': common_count
                                    })
                        
                        # Sort by score desc, then by recency
                        sorted_posts = sorted(posts_with_scores, key=lambda x: (-x['score'], x['index']))
                        post_ids = [p['id'] for p in sorted_posts[:limit]]
                        
                        # Fill with recent posts if needed
                        if len(post_ids) < limit:
                            additional = [p['id'] for p in valid_posts_with_data if p['id'] not in post_ids]
                            post_ids.extend(additional[:limit - len(post_ids)])
                    else:
                        # Fallback to SQL query when Redis data not available yet
                        self.logger.info(f"Mode {mode} - Redis cache for interests/topics not available yet, using SQL")
                        with self.db.engine.begin() as connection:
                            query = text("""
                                SELECT DISTINCT p.id
                                FROM post p
                                INNER JOIN post_topic pt ON p.id = pt.post_id
                                INNER JOIN user_interest ui ON pt.topic_id = ui.topic_id
                                WHERE ui.user_id = :agent_id AND p.user_id != :agent_id
                                ORDER BY p.id DESC
                                LIMIT :limit
                            """)
                            result = connection.execute(query, {"agent_id": agent_id, "limit": limit})
                            sql_post_ids = [row[0] for row in result]
                            post_ids = [pid for pid in sql_post_ids if pid in all_post_ids][:limit]
                            
                            if len(post_ids) < limit:
                                additional = [p['id'] for p in valid_posts_with_data if p['id'] not in post_ids]
                                post_ids.extend(additional[:limit - len(post_ids)])
                
                elif mode == "common_user_interests":
                    # Posts interacted with by users who share interests
                    # Assumes Redis: ysim:user:{user_id}:interests (set), ysim:reaction:{reaction_id} (hash)
                    
                    user_interests_key = self.db._redis_key("user", agent_id) + ":interests"
                    if self.db.redis_client.exists(user_interests_key):
                        # Redis implementation when data is available
                        user_interests = self.db.redis_client.smembers(user_interests_key)
                        
                        # Find users with common interests
                        user_ids_key = self.db._redis_key("user_mgmt", "ids")
                        all_user_ids = self.db.redis_client.smembers(user_ids_key) if self.db.redis_client.exists(user_ids_key) else []
                        
                        similar_users = set()
                        for uid in all_user_ids:
                            if uid != agent_id:
                                other_interests_key = self.db._redis_key("user", uid) + ":interests"
                                if self.db.redis_client.exists(other_interests_key):
                                    other_interests = self.db.redis_client.smembers(other_interests_key)
                                    if len(user_interests & other_interests) > 0:
                                        similar_users.add(uid)
                        
                        # Get posts liked by similar users
                        posts_with_scores = []
                        post_id_to_data = {all_post_ids[i]: posts_data[i] for i in range(len(all_post_ids))}
                        
                        for post in valid_posts_with_data:
                            # Check if any similar user liked this post
                            # Future: Redis will cache reactions by post
                            post_reactions_key = self.db._redis_key("post", post['id']) + ":reactions"
                            if self.db.redis_client.exists(post_reactions_key):
                                reaction_user_ids = self.db.redis_client.smembers(post_reactions_key)
                                common_users = similar_users & reaction_user_ids
                                if common_users:
                                    posts_with_scores.append({
                                        'id': post['id'],
                                        'index': post['index'],
                                        'score': len(common_users)
                                    })
                        
                        sorted_posts = sorted(posts_with_scores, key=lambda x: (-x['score'], x['index']))
                        post_ids = [p['id'] for p in sorted_posts[:limit]]
                        
                        if len(post_ids) < limit:
                            additional = [p['id'] for p in valid_posts_with_data if p['id'] not in post_ids]
                            post_ids.extend(additional[:limit - len(post_ids)])
                    else:
                        # Fallback to SQL
                        self.logger.info(f"Mode {mode} - Redis cache for interests not available yet, using SQL")
                        with self.db.engine.begin() as connection:
                            query = text("""
                                SELECT DISTINCT p.id
                                FROM post p
                                INNER JOIN reaction r ON p.id = r.post_id
                                INNER JOIN user_interest ui1 ON r.user_id = ui1.user_id
                                INNER JOIN user_interest ui2 ON ui1.topic_id = ui2.topic_id
                                WHERE ui2.user_id = :agent_id 
                                    AND r.user_id != :agent_id 
                                    AND p.user_id != :agent_id
                                    AND r.type = 'like'
                                ORDER BY p.id DESC
                                LIMIT :limit
                            """)
                            result = connection.execute(query, {"agent_id": agent_id, "limit": limit})
                            sql_post_ids = [row[0] for row in result]
                            post_ids = [pid for pid in sql_post_ids if pid in all_post_ids][:limit]
                            
                            if len(post_ids) < limit:
                                additional = [p['id'] for p in valid_posts_with_data if p['id'] not in post_ids]
                                post_ids.extend(additional[:limit - len(post_ids)])
                
                elif mode in ["similar_users_react", "similar_users_posts"]:
                    # These modes use user demographics which should be in Redis user hashes
                    # Assumes Redis: ysim:users:{user_id} has age_group, gender, leaning fields
                    
                    # Get agent demographics from Redis
                    agent_key = self.db._redis_key("users", agent_id)
                    agent_data = self.db.redis_client.hgetall(agent_key) if self.db.redis_client.exists(agent_key) else {}
                    
                    if agent_data:
                        # Redis implementation using cached user data
                        agent_age_group = agent_data.get('age_group')
                        agent_gender = agent_data.get('gender')
                        agent_leaning = agent_data.get('leaning')
                        
                        # Create mapping
                        post_id_to_data = {all_post_ids[i]: posts_data[i] for i in range(len(all_post_ids))}
                        
                        if mode == "similar_users_react":
                            # Get posts liked by similar users
                            # Future: Redis will cache reactions with user_id
                            posts_with_scores = []
                            for post in valid_posts_with_data:
                                # Check reactions for this post
                                post_reactions_key = self.db._redis_key("post", post['id']) + ":reactions"
                                if self.db.redis_client.exists(post_reactions_key):
                                    reaction_user_ids = self.db.redis_client.smembers(post_reactions_key)
                                    similar_count = 0
                                    for uid in reaction_user_ids:
                                        user_key = self.db._redis_key("users", uid)
                                        user_data = self.db.redis_client.hgetall(user_key) if self.db.redis_client.exists(user_key) else {}
                                        if user_data:
                                            # Check similarity
                                            if (user_data.get('age_group') == agent_age_group or
                                                user_data.get('gender') == agent_gender or
                                                user_data.get('leaning') == agent_leaning):
                                                similar_count += 1
                                    
                                    if similar_count > 0:
                                        posts_with_scores.append({
                                            'id': post['id'],
                                            'index': post['index'],
                                            'score': similar_count
                                        })
                            
                            sorted_posts = sorted(posts_with_scores, key=lambda x: (-x['score'], x['index']))
                            post_ids = [p['id'] for p in sorted_posts[:limit]]
                        else:  # similar_users_posts
                            # Get posts from similar users
                            posts_with_similarity = []
                            for post in valid_posts_with_data:
                                post_data = post_id_to_data.get(post['id'])
                                if post_data:
                                    author_id = post_data.get('user_id')
                                    if author_id and author_id != agent_id:
                                        author_key = self.db._redis_key("users", author_id)
                                        author_data = self.db.redis_client.hgetall(author_key) if self.db.redis_client.exists(author_key) else {}
                                        if author_data:
                                            similarity_score = 0
                                            if author_data.get('age_group') == agent_age_group:
                                                similarity_score += 1
                                            if author_data.get('gender') == agent_gender:
                                                similarity_score += 1
                                            if author_data.get('leaning') == agent_leaning:
                                                similarity_score += 1
                                            
                                            if similarity_score > 0:
                                                posts_with_similarity.append({
                                                    'id': post['id'],
                                                    'index': post['index'],
                                                    'score': similarity_score
                                                })
                            
                            sorted_posts = sorted(posts_with_similarity, key=lambda x: (-x['score'], x['index']))
                            post_ids = [p['id'] for p in sorted_posts[:limit]]
                        
                        # Fill with recent posts if needed
                        if len(post_ids) < limit:
                            additional = [p['id'] for p in valid_posts_with_data if p['id'] not in post_ids]
                            post_ids.extend(additional[:limit - len(post_ids)])
                    else:
                        # Fallback to SQL query
                        self.logger.info(f"Mode {mode} - Using SQL for user demographics query")
                        with self.db.engine.begin() as connection:
                            if mode == "similar_users_react":
                                query = text("""
                                    SELECT DISTINCT p.id
                                    FROM post p
                                    INNER JOIN reaction r ON p.id = r.post_id
                                    INNER JOIN user_mgmt um ON r.user_id = um.id
                                    INNER JOIN user_mgmt target ON target.id = :agent_id
                                    WHERE p.user_id != :agent_id
                                        AND um.id != :agent_id
                                        AND r.type = 'like'
                                        AND (
                                            (um.age_group = target.age_group) OR
                                            (um.gender = target.gender) OR
                                            (um.leaning = target.leaning)
                                        )
                                    ORDER BY p.id DESC
                                    LIMIT :limit
                                """)
                            else:  # similar_users_posts
                                query = text("""
                                    SELECT p.id
                                    FROM post p
                                    INNER JOIN user_mgmt um ON p.user_id = um.id
                                    INNER JOIN user_mgmt target ON target.id = :agent_id
                                    WHERE p.user_id != :agent_id
                                        AND (
                                            (um.age_group = target.age_group) OR
                                            (um.gender = target.gender) OR
                                            (um.leaning = target.leaning)
                                        )
                                    ORDER BY p.id DESC
                                    LIMIT :limit
                                """)
                            
                            result = connection.execute(query, {"agent_id": agent_id, "limit": limit})
                            sql_post_ids = [row[0] for row in result]
                            post_ids = [pid for pid in sql_post_ids if pid in all_post_ids][:limit]
                            
                            if len(post_ids) < limit:
                                additional = [p['id'] for p in valid_posts_with_data if p['id'] not in post_ids]
                                post_ids.extend(additional[:limit - len(post_ids)])

                    
                else:
                    # Random ordering (default for Redis)
                    if len(valid_posts_with_data) > limit:
                        selected = random.sample(valid_posts_with_data, limit)
                        post_ids = [p['id'] for p in selected]
                    else:
                        post_ids = [p['id'] for p in valid_posts_with_data]
                
                self.logger.info(
                    f"Recommended {len(post_ids)} posts (Redis, mode={mode})",
                    extra={
                        "extra_data": {
                            "agent_id": agent_id,
                            "mode": mode,
                            "limit": limit,
                            "found": len(post_ids),
                        }
                    },
                )
                
                # Save recommendations to database (and Redis if enabled)
                self._save_recommendation(agent_id, post_ids)
                
                return post_ids
                
            else:
                # Use SQL database for recommendations
                with self.db.engine.begin() as connection:
                    
                    if mode == "rchrono":
                        # Reverse chronological: newest posts first
                        query = text("""
                            SELECT p.id FROM post p
                            INNER JOIN rounds rd ON p.round = rd.id
                            WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                                AND p.user_id != :agent_id
                            ORDER BY rd.day DESC, rd.hour DESC
                            LIMIT :limit
                        """)
                        result = connection.execute(query, {
                            "vis_day": visibility_day,
                            "vis_hour": visibility_hour,
                            "agent_id": agent_id,
                            "limit": limit
                        })
                        post_ids = [row[0] for row in result]
                        
                    elif mode == "rchrono_popularity":
                        # Reverse chronological with popularity (reaction count)
                        query = text("""
                            SELECT p.id 
                            FROM post p
                            INNER JOIN rounds rd ON p.round = rd.id
                            LEFT JOIN (
                                SELECT post_id, COUNT(*) as reaction_count
                                FROM reaction
                                GROUP BY post_id
                            ) r ON p.id = r.post_id
                            WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                                AND p.user_id != :agent_id
                            ORDER BY rd.day DESC, rd.hour DESC, COALESCE(r.reaction_count, 0) DESC
                            LIMIT :limit
                        """)
                        result = connection.execute(query, {
                            "vis_day": visibility_day,
                            "vis_hour": visibility_hour,
                            "agent_id": agent_id,
                            "limit": limit
                        })
                        post_ids = [row[0] for row in result]
                        
                    elif mode == "rchrono_followers":
                        # Prioritize posts from followed users
                        # Note: user_id is the one being followed, follower_id is the one following
                        follower_posts_limit = int(limit * followers_ratio)
                        additional_posts_limit = limit - follower_posts_limit
                        
                        # Get posts from followed users
                        query_followers = text("""
                            SELECT DISTINCT p.id 
                            FROM post p
                            INNER JOIN rounds rd ON p.round = rd.id
                            INNER JOIN follow f ON p.user_id = f.follower_id
                            WHERE f.user_id = :agent_id 
                                AND f.action = 'follow'
                                AND (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                                AND p.user_id != :agent_id
                            ORDER BY rd.day DESC, rd.hour DESC
                            LIMIT :follower_limit
                        """)
                        result = connection.execute(query_followers, {
                            "agent_id": agent_id,
                            "vis_day": visibility_day,
                            "vis_hour": visibility_hour,
                            "follower_limit": follower_posts_limit
                        })
                        post_ids = [row[0] for row in result]
                        
                        # If we need more posts, get additional ones
                        if len(post_ids) < limit and additional_posts_limit > 0:
                            # Use conditional query based on whether we have existing IDs
                            if post_ids:
                                query_additional = text("""
                                    SELECT p.id FROM post p
                                    INNER JOIN rounds rd ON p.round = rd.id
                                    WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                                        AND p.user_id != :agent_id
                                        AND p.id NOT IN :existing_ids
                                    ORDER BY rd.day DESC, rd.hour DESC
                                    LIMIT :additional_limit
                                """)
                                result = connection.execute(query_additional, {
                                    "vis_day": visibility_day,
                                    "vis_hour": visibility_hour,
                                    "agent_id": agent_id,
                                    "existing_ids": tuple(post_ids),
                                    "additional_limit": additional_posts_limit
                                })
                            else:
                                # No existing posts, skip the NOT IN clause
                                query_additional = text("""
                                    SELECT p.id FROM post p
                                    INNER JOIN rounds rd ON p.round = rd.id
                                    WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                                        AND p.user_id != :agent_id
                                    ORDER BY rd.day DESC, rd.hour DESC
                                    LIMIT :additional_limit
                                """)
                                result = connection.execute(query_additional, {
                                    "vis_day": visibility_day,
                                    "vis_hour": visibility_hour,
                                    "agent_id": agent_id,
                                    "additional_limit": additional_posts_limit
                                })
                            post_ids.extend([row[0] for row in result])
                        
                    elif mode == "rchrono_followers_popularity":
                        # Followers with popularity boost
                        follower_posts_limit = int(limit * followers_ratio)
                        additional_posts_limit = limit - follower_posts_limit
                        
                        query_followers = text("""
                            SELECT DISTINCT p.id 
                            FROM post p
                            INNER JOIN rounds rd ON p.round = rd.id
                            INNER JOIN follow f ON p.user_id = f.follower_id
                            LEFT JOIN (
                                SELECT post_id, COUNT(*) as reaction_count
                                FROM reaction
                                GROUP BY post_id
                            ) r ON p.id = r.post_id
                            WHERE f.user_id = :agent_id 
                                AND f.action = 'follow'
                                AND (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                                AND p.user_id != :agent_id
                            ORDER BY p.round DESC, COALESCE(r.reaction_count, 0) DESC
                            LIMIT :follower_limit
                        """)
                        result = connection.execute(query_followers, {
                            "agent_id": agent_id,
                            "vis_day": visibility_day,
                            "vis_hour": visibility_hour,
                            "follower_limit": follower_posts_limit
                        })
                        post_ids = [row[0] for row in result]
                        
                        if len(post_ids) < limit and additional_posts_limit > 0:
                            if post_ids:
                                query_additional = text("""
                                    SELECT p.id 
                                    FROM post p
                                    INNER JOIN rounds rd ON p.round = rd.id
                                    LEFT JOIN (
                                        SELECT post_id, COUNT(*) as reaction_count
                                        FROM reaction
                                        GROUP BY post_id
                                    ) r ON p.id = r.post_id
                                    WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour)) 
                                        AND p.user_id != :agent_id
                                        AND p.id NOT IN :existing_ids
                                    ORDER BY p.round DESC, COALESCE(r.reaction_count, 0) DESC
                                    LIMIT :additional_limit
                                """)
                                result = connection.execute(query_additional, {
                                    "vis_day": visibility_day,
                                    "vis_hour": visibility_hour,
                                    "agent_id": agent_id,
                                    "existing_ids": tuple(post_ids),
                                    "additional_limit": additional_posts_limit
                                })
                            else:
                                query_additional = text("""
                                    SELECT p.id 
                                    FROM post p
                                    INNER JOIN rounds rd ON p.round = rd.id
                                    LEFT JOIN (
                                        SELECT post_id, COUNT(*) as reaction_count
                                        FROM reaction
                                        GROUP BY post_id
                                    ) r ON p.id = r.post_id
                                    WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour)) 
                                        AND p.user_id != :agent_id
                                    ORDER BY p.round DESC, COALESCE(r.reaction_count, 0) DESC
                                    LIMIT :additional_limit
                                """)
                                result = connection.execute(query_additional, {
                                    "vis_day": visibility_day,
                                    "vis_hour": visibility_hour,
                                    "agent_id": agent_id,
                                    "additional_limit": additional_posts_limit
                                })
                            post_ids.extend([row[0] for row in result])
                            
                    elif mode == "rchrono_comments":
                        # Prioritize posts with more comments (thread activity)
                        # Count comments by checking posts that reference this post via comment_to
                        query = text("""
                            SELECT p.id
                            FROM post p
                            INNER JOIN rounds rd ON p.round = rd.id
                            LEFT JOIN post c ON p.id = c.comment_to
                            WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                                AND p.user_id != :agent_id
                                AND p.comment_to IS NULL
                            GROUP BY p.id
                            ORDER BY COUNT(c.id) DESC, rd.day DESC, rd.hour DESC
                            LIMIT :limit
                        """)
                        result = connection.execute(query, {
                            "vis_day": visibility_day,
                            "vis_hour": visibility_hour,
                            "agent_id": agent_id,
                            "limit": limit
                        })
                        post_ids = [row[0] for row in result]
                        
                    elif mode == "common_interests":
                        # Posts with common topic interests
                        # This requires PostTopic and UserInterest tables
                        follower_posts_limit = int(limit * followers_ratio)
                        additional_posts_limit = limit - follower_posts_limit
                        
                        # Get posts matching user's interests from followers
                        query = text("""
                            SELECT DISTINCT p.id
                            FROM post p
                            INNER JOIN rounds rd ON p.round = rd.id
                            INNER JOIN post_topics pt ON p.id = pt.post_id
                            INNER JOIN user_interest ui ON pt.topic_id = ui.interest_id
                            INNER JOIN follow f ON p.user_id = f.follower_id
                            WHERE ui.user_id = :agent_id
                                AND f.user_id = :agent_id
                                AND f.action = 'follow'
                                AND (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                                AND p.user_id != :agent_id
                            GROUP BY p.id
                            ORDER BY COUNT(pt.topic_id) DESC, rd.day DESC, rd.hour DESC
                            LIMIT :follower_limit
                        """)
                        result = connection.execute(query, {
                            "agent_id": agent_id,
                            "vis_day": visibility_day,
                            "vis_hour": visibility_hour,
                            "follower_limit": follower_posts_limit
                        })
                        post_ids = [row[0] for row in result]
                        
                        # Get additional posts with common interests
                        if len(post_ids) < limit and additional_posts_limit > 0:
                            if post_ids:
                                query_additional = text("""
                                    SELECT DISTINCT p.id
                                    FROM post p
                                    INNER JOIN rounds rd ON p.round = rd.id
                                    INNER JOIN post_topics pt ON p.id = pt.post_id
                                    INNER JOIN user_interest ui ON pt.topic_id = ui.interest_id
                                    WHERE ui.user_id = :agent_id
                                        AND (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                                        AND p.user_id != :agent_id
                                        AND p.id NOT IN :existing_ids
                                    GROUP BY p.id
                                    ORDER BY COUNT(pt.topic_id) DESC, rd.day DESC, rd.hour DESC
                                    LIMIT :additional_limit
                                """)
                                result = connection.execute(query_additional, {
                                    "agent_id": agent_id,
                                    "vis_day": visibility_day,
                                    "vis_hour": visibility_hour,
                                    "existing_ids": tuple(post_ids),
                                    "additional_limit": additional_posts_limit
                                })
                            else:
                                query_additional = text("""
                                    SELECT DISTINCT p.id
                                    FROM post p
                                    INNER JOIN rounds rd ON p.round = rd.id
                                    INNER JOIN post_topics pt ON p.id = pt.post_id
                                    INNER JOIN user_interest ui ON pt.topic_id = ui.interest_id
                                    WHERE ui.user_id = :agent_id
                                        AND (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                                        AND p.user_id != :agent_id
                                    GROUP BY p.id
                                    ORDER BY COUNT(pt.topic_id) DESC, rd.day DESC, rd.hour DESC
                                    LIMIT :additional_limit
                                """)
                                result = connection.execute(query_additional, {
                                    "agent_id": agent_id,
                                    "vis_day": visibility_day,
                                    "vis_hour": visibility_hour,
                                    "additional_limit": additional_posts_limit
                                })
                            post_ids.extend([row[0] for row in result])
                    
                    elif mode == "common_user_interests":
                        # Posts by users with common interests (most interacted)
                        follower_posts_limit = int(limit * followers_ratio)
                        additional_posts_limit = limit - follower_posts_limit
                        
                        # Get posts reacted to by users with common interests who are followers
                        query = text("""
                            SELECT DISTINCT p.id, COUNT(r.id) as reaction_count
                            FROM post p
                            INNER JOIN rounds rd ON p.round = rd.id
                            INNER JOIN reaction r ON p.id = r.post_id
                            INNER JOIN user_mgmt um ON r.user_id = um.id
                            INNER JOIN user_interest ui1 ON um.id = ui1.user_id
                            INNER JOIN user_interest ui2 ON ui1.interest_id = ui2.interest_id
                            INNER JOIN follow f ON um.id = f.follower_id
                            WHERE ui2.user_id = :agent_id
                                AND f.user_id = :agent_id
                                AND f.action = 'follow'
                                AND (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                                AND p.user_id != :agent_id
                            GROUP BY p.id
                            ORDER BY reaction_count DESC, rd.day DESC, rd.hour DESC
                            LIMIT :follower_limit
                        """)
                        result = connection.execute(query, {
                            "agent_id": agent_id,
                            "vis_day": visibility_day,
                            "vis_hour": visibility_hour,
                            "follower_limit": follower_posts_limit
                        })
                        post_ids = [row[0] for row in result]
                        
                        # Get additional from non-followers with common interests
                        if len(post_ids) < limit and additional_posts_limit > 0:
                            if post_ids:
                                query_additional = text("""
                                    SELECT DISTINCT p.id, COUNT(r.id) as reaction_count
                                    FROM post p
                                    INNER JOIN rounds rd ON p.round = rd.id
                                    INNER JOIN reaction r ON p.id = r.post_id
                                    INNER JOIN user_mgmt um ON r.user_id = um.id
                                    INNER JOIN user_interest ui1 ON um.id = ui1.user_id
                                    INNER JOIN user_interest ui2 ON ui1.interest_id = ui2.interest_id
                                    WHERE ui2.user_id = :agent_id
                                        AND (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                                        AND p.user_id != :agent_id
                                        AND p.id NOT IN :existing_ids
                                    GROUP BY p.id
                                    ORDER BY reaction_count DESC, rd.day DESC, rd.hour DESC
                                    LIMIT :additional_limit
                                """)
                                result = connection.execute(query_additional, {
                                    "agent_id": agent_id,
                                    "vis_day": visibility_day,
                                    "vis_hour": visibility_hour,
                                    "existing_ids": tuple(post_ids),
                                    "additional_limit": additional_posts_limit
                                })
                                post_ids.extend([row[0] for row in result])
                    
                    elif mode == "similar_users_react":
                        # Posts from similar users (based on demographics/personality)
                        # Find similar users and get posts they reacted to
                        query = text("""
                            SELECT DISTINCT p.id
                            FROM post p
                            INNER JOIN rounds rd ON p.round = rd.id
                            INNER JOIN reaction r ON p.id = r.post_id
                            INNER JOIN user_mgmt um ON r.user_id = um.id
                            INNER JOIN user_mgmt target ON target.id = :agent_id
                            WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                                AND p.user_id != :agent_id
                                AND um.id != :agent_id
                                AND r.type = 'like'
                                AND (
                                    (um.age_group = target.age_group) OR
                                    (um.gender = target.gender) OR
                                    (um.leaning = target.leaning)
                                )
                            GROUP BY p.id
                            ORDER BY rd.day DESC, rd.hour DESC
                            LIMIT :limit
                        """)
                        result = connection.execute(query, {
                            "agent_id": agent_id,
                            "vis_day": visibility_day,
                            "vis_hour": visibility_hour,
                            "limit": limit
                        })
                        post_ids = [row[0] for row in result]
                    
                    elif mode == "similar_users_posts":
                        # Posts created by similar users
                        query = text("""
                            SELECT p.id
                            FROM post p
                            INNER JOIN rounds rd ON p.round = rd.id
                            INNER JOIN user_mgmt um ON p.user_id = um.id
                            INNER JOIN user_mgmt target ON target.id = :agent_id
                            WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                                AND p.user_id != :agent_id
                                AND (
                                    (um.age_group = target.age_group) OR
                                    (um.gender = target.gender) OR
                                    (um.leaning = target.leaning)
                                )
                            ORDER BY rd.day DESC, rd.hour DESC
                            LIMIT :limit
                        """)
                        result = connection.execute(query, {
                            "agent_id": agent_id,
                            "vis_day": visibility_day,
                            "vis_hour": visibility_hour,
                            "limit": limit
                        })
                        post_ids = [row[0] for row in result]
                        
                    else:
                        # Random ordering (default)
                        # Note: RANDOM() works for SQLite and PostgreSQL
                        # For MySQL, use RAND() instead
                        query = text("""
                            SELECT p.id FROM post p
                            INNER JOIN rounds rd ON p.round = rd.id
                            WHERE (rd.day > :vis_day OR (rd.day = :vis_day AND rd.hour >= :vis_hour))
                                AND p.user_id != :agent_id
                            ORDER BY RANDOM()
                            LIMIT :limit
                        """)
                        result = connection.execute(query, {
                            "vis_day": visibility_day,
                            "vis_hour": visibility_hour,
                            "agent_id": agent_id,
                            "limit": limit
                        })
                        post_ids = [row[0] for row in result]
                    
                    self.logger.info(
                        f"Recommended {len(post_ids)} posts (SQL, mode={mode})",
                        extra={
                            "extra_data": {
                                "agent_id": agent_id,
                                "mode": mode,
                                "limit": limit,
                                "found": len(post_ids),
                            }
                        },
                    )
                    
                    # Save recommendations to database (and Redis if enabled)
                    self._save_recommendation(agent_id, post_ids)
                    
                    return post_ids
                
        except Exception as e:
            self.logger.error(
                f"Error getting recommended posts: {e}",
                extra={"extra_data": {"agent_id": agent_id, "mode": mode, "error": str(e)}},
            )
            return []
    
    def get_post(self, post_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a post by its ID.
        
        Args:
            post_id: UUID of the post to retrieve
            
        Returns:
            Dictionary with post data or None if not found
        """
        return self.db.get_post(post_id)

    def get_follow_suggestions(
        self,
        agent_id: str,
        mode: str = "random",
        n_neighbors: int = 10,
        leaning_bias: int = 1
    ) -> List[str]:
        """
        Get follow suggestions for an agent using the specified recommendation strategy.
        
        This method implements various link prediction and recommendation algorithms
        using efficient query-based approaches for scalability.
        
        Args:
            agent_id: UUID of the agent requesting follow suggestions
            mode: Recommendation mode:
                - "random": Random user suggestions (default)
                - "common_neighbors": Users with mutual connections
                - "jaccard": Jaccard coefficient-based similarity
                - "adamic_adar": Adamic/Adar index for link prediction
                - "preferential_attachment": Rich-get-richer recommendation
            n_neighbors: Number of users to suggest (default: 10)
            leaning_bias: Political leaning bias factor (1 = no bias, higher = more homophily)
            
        Returns:
            List[str]: List of user UUIDs recommended for the agent to follow
        """
        if self.db.use_redis:
            return self._get_follow_suggestions_redis(agent_id, mode, n_neighbors, leaning_bias)
        else:
            return self._get_follow_suggestions_sql(agent_id, mode, n_neighbors, leaning_bias)
    
    def _get_follow_suggestions_sql(
        self,
        agent_id: str,
        mode: str,
        n_neighbors: int,
        leaning_bias: int
    ) -> List[str]:
        """
        Get follow suggestions using SQL queries for better scalability.
        """
        try:
            from sqlalchemy.orm import Session
            from YSimulator.YServer.classes.models import User_mgmt, Follow
            from sqlalchemy import func, and_, or_
            
            with Session(self.db.engine) as session:
                # Get agent's info for leaning-based filtering
                agent = session.query(User_mgmt).filter_by(id=agent_id).first()
                if not agent:
                    self.logger.warning(f"Agent {agent_id} not found for follow suggestions")
                    return []
                
                # Get users that agent is currently following (with latest action = "follow")
                # Subquery to get latest follow action per user pair
                latest_follows_subq = session.query(
                    Follow.follower_id,
                    Follow.user_id,
                    func.max(Follow.round).label('max_round')
                ).filter(
                    Follow.follower_id == agent_id
                ).group_by(Follow.follower_id, Follow.user_id).subquery()
                
                following = session.query(Follow.user_id).join(
                    latest_follows_subq,
                    and_(
                        Follow.follower_id == latest_follows_subq.c.follower_id,
                        Follow.user_id == latest_follows_subq.c.user_id,
                        Follow.round == latest_follows_subq.c.max_round,
                        Follow.action == "follow"
                    )
                ).all()
                following_ids = {f.user_id for f in following}
                
                # Get candidate users (not following, not self)
                candidates_query = session.query(User_mgmt.id, User_mgmt.leaning).filter(
                    User_mgmt.id != agent_id,
                    User_mgmt.id.notin_(following_ids) if following_ids else True
                )
                
                if mode == "random":
                    # Random selection from candidates
                    candidates = candidates_query.all()
                    if not candidates:
                        return []
                    
                    candidate_ids = [c.id for c in candidates]
                    random.shuffle(candidate_ids)
                    suggestions = candidate_ids[:n_neighbors]
                    
                elif mode == "common_neighbors":
                    # Find users with most mutual connections (friend-of-friend)
                    # Users that agent's friends also follow
                    if not following_ids:
                        # No one to compute common neighbors with, fallback to random
                        candidates = candidates_query.all()
                        candidate_ids = [c.id for c in candidates]
                        random.shuffle(candidate_ids)
                        return candidate_ids[:n_neighbors]
                    
                    # SQL query to count common neighbors
                    common_neighbors = text("""
                        SELECT f2.user_id, COUNT(DISTINCT f2.follower_id) as common_count
                        FROM follow f1
                        JOIN follow f2 ON f1.user_id = f2.follower_id
                        WHERE f1.follower_id = :agent_id
                          AND f1.action = 'follow'
                          AND f2.action = 'follow'
                          AND f2.user_id != :agent_id
                          AND f2.user_id NOT IN :following_ids
                        GROUP BY f2.user_id
                        ORDER BY common_count DESC
                        LIMIT :limit
                    """)
                    
                    # Handle empty following_ids case for SQL
                    following_list = list(following_ids) if following_ids else [agent_id]
                    
                    result = session.execute(
                        common_neighbors,
                        {
                            "agent_id": agent_id,
                            "following_ids": tuple(following_list),
                            "limit": n_neighbors
                        }
                    )
                    suggestions = [row[0] for row in result]
                    
                    # If not enough suggestions, add random ones
                    if len(suggestions) < n_neighbors:
                        remaining = n_neighbors - len(suggestions)
                        extra_candidates = candidates_query.filter(
                            User_mgmt.id.notin_(suggestions) if suggestions else True
                        ).limit(remaining * 2).all()
                        extra_ids = [c.id for c in extra_candidates]
                        random.shuffle(extra_ids)
                        suggestions.extend(extra_ids[:remaining])
                    
                elif mode == "jaccard":
                    # Jaccard similarity: intersection over union of follow sets
                    if not following_ids:
                        # No one to compute similarity with, fallback to random
                        candidates = candidates_query.all()
                        candidate_ids = [c.id for c in candidates]
                        random.shuffle(candidate_ids)
                        return candidate_ids[:n_neighbors]
                    
                    # This is complex in pure SQL, use a simplified approach:
                    # Score by common neighbors normalized by total unique neighbors
                    jaccard_query = text("""
                        SELECT 
                            candidate_id,
                            CAST(common_count AS FLOAT) / NULLIF(union_count, 0) as jaccard_score
                        FROM (
                            SELECT 
                                f2.user_id as candidate_id,
                                COUNT(DISTINCT CASE WHEN f1.user_id = f2.follower_id THEN f1.user_id END) as common_count,
                                COUNT(DISTINCT f1.user_id) + COUNT(DISTINCT f3.user_id) as union_count
                            FROM follow f1
                            CROSS JOIN follow f2
                            LEFT JOIN follow f3 ON f2.user_id = f3.follower_id AND f3.action = 'follow'
                            WHERE f1.follower_id = :agent_id
                              AND f1.action = 'follow'
                              AND f2.action = 'follow'
                              AND f2.user_id != :agent_id
                              AND f2.user_id NOT IN :following_ids
                            GROUP BY f2.user_id
                        ) subq
                        ORDER BY jaccard_score DESC
                        LIMIT :limit
                    """)
                    
                    following_list = list(following_ids) if following_ids else [agent_id]
                    result = session.execute(
                        jaccard_query,
                        {
                            "agent_id": agent_id,
                            "following_ids": tuple(following_list),
                            "limit": n_neighbors
                        }
                    )
                    suggestions = [row[0] for row in result]
                    
                    # Fill with random if needed
                    if len(suggestions) < n_neighbors:
                        remaining = n_neighbors - len(suggestions)
                        extra_candidates = candidates_query.filter(
                            User_mgmt.id.notin_(suggestions) if suggestions else True
                        ).limit(remaining * 2).all()
                        extra_ids = [c.id for c in extra_candidates]
                        random.shuffle(extra_ids)
                        suggestions.extend(extra_ids[:remaining])
                    
                elif mode == "adamic_adar":
                    # Adamic/Adar: sum of 1/log(degree) for common neighbors
                    # Two-step approach: 1) Find common neighbors, 2) Calculate Adamic/Adar scores
                    if not following_ids:
                        candidates = candidates_query.all()
                        candidate_ids = [c.id for c in candidates]
                        random.shuffle(candidate_ids)
                        return candidate_ids[:n_neighbors]
                    
                    # Step 1: Get common neighbors (friend-of-friend) candidates
                    common_neighbors_query = text("""
                        SELECT f2.user_id, f2.follower_id as common_neighbor
                        FROM follow f1
                        JOIN follow f2 ON f1.user_id = f2.follower_id
                        WHERE f1.follower_id = :agent_id
                          AND f1.action = 'follow'
                          AND f2.action = 'follow'
                          AND f2.user_id != :agent_id
                          AND f2.user_id NOT IN :following_ids
                    """)
                    
                    following_list = list(following_ids) if following_ids else [agent_id]
                    result = session.execute(
                        common_neighbors_query,
                        {
                            "agent_id": agent_id,
                            "following_ids": tuple(following_list)
                        }
                    )
                    
                    # Build mapping of candidate -> list of common neighbors
                    candidate_common_neighbors = {}
                    for row in result:
                        candidate_id, common_neighbor = row
                        if candidate_id not in candidate_common_neighbors:
                            candidate_common_neighbors[candidate_id] = []
                        candidate_common_neighbors[candidate_id].append(common_neighbor)
                    
                    if not candidate_common_neighbors:
                        # No common neighbors found, fallback to random
                        candidates = candidates_query.all()
                        candidate_ids = [c.id for c in candidates]
                        random.shuffle(candidate_ids)
                        return candidate_ids[:n_neighbors]
                    
                    # Step 2: Calculate Adamic/Adar score for each candidate
                    # For each common neighbor, get their degree (out-degree = users they follow)
                    common_neighbor_ids = set()
                    for neighbors in candidate_common_neighbors.values():
                        common_neighbor_ids.update(neighbors)
                    
                    # Query to get degree for each common neighbor
                    degree_query = text("""
                        SELECT follower_id, COUNT(*) as out_degree
                        FROM follow
                        WHERE follower_id IN :neighbor_ids
                          AND action = 'follow'
                        GROUP BY follower_id
                    """)
                    
                    degree_result = session.execute(
                        degree_query,
                        {"neighbor_ids": tuple(common_neighbor_ids)}
                    )
                    
                    # Build degree map
                    neighbor_degrees = {row[0]: row[1] for row in degree_result}
                    
                    # Calculate Adamic/Adar score for each candidate
                    import math
                    adamic_adar_scores = {}
                    for candidate_id, neighbors in candidate_common_neighbors.items():
                        score = 0.0
                        for neighbor in neighbors:
                            degree = neighbor_degrees.get(neighbor, 1)  # Default to 1 to avoid division by zero
                            if degree > 1:  # Only count if degree > 1 (log(1) = 0)
                                score += 1.0 / math.log(degree)
                        adamic_adar_scores[candidate_id] = score
                    
                    # Sort by Adamic/Adar score (highest first)
                    sorted_candidates = sorted(adamic_adar_scores.items(), key=lambda x: x[1], reverse=True)
                    suggestions = [uid for uid, score in sorted_candidates[:n_neighbors]]
                    
                    # Fill with random if needed
                    if len(suggestions) < n_neighbors:
                        remaining = n_neighbors - len(suggestions)
                        extra_candidates = candidates_query.filter(
                            User_mgmt.id.notin_(suggestions) if suggestions else True
                        ).limit(remaining * 2).all()
                        extra_ids = [c.id for c in extra_candidates]
                        random.shuffle(extra_ids)
                        suggestions.extend(extra_ids[:remaining])
                    
                elif mode == "preferential_attachment":
                    # Prefer users with many followers (popularity-based)
                    popular_users = text("""
                        SELECT f.user_id, COUNT(*) as follower_count
                        FROM follow f
                        WHERE f.action = 'follow'
                          AND f.user_id != :agent_id
                          AND f.user_id NOT IN :following_ids
                        GROUP BY f.user_id
                        ORDER BY follower_count DESC
                        LIMIT :limit
                    """)
                    
                    following_list = list(following_ids) if following_ids else [agent_id]
                    result = session.execute(
                        popular_users,
                        {
                            "agent_id": agent_id,
                            "following_ids": tuple(following_list),
                            "limit": n_neighbors
                        }
                    )
                    suggestions = [row[0] for row in result]
                    
                    if len(suggestions) < n_neighbors:
                        remaining = n_neighbors - len(suggestions)
                        extra_candidates = candidates_query.filter(
                            User_mgmt.id.notin_(suggestions) if suggestions else True
                        ).limit(remaining * 2).all()
                        extra_ids = [c.id for c in extra_candidates]
                        random.shuffle(extra_ids)
                        suggestions.extend(extra_ids[:remaining])
                    
                else:
                    # Unknown mode, fallback to random
                    candidates = candidates_query.all()
                    candidate_ids = [c.id for c in candidates]
                    random.shuffle(candidate_ids)
                    suggestions = candidate_ids[:n_neighbors]
                
                # Apply leaning bias if > 1
                if leaning_bias > 1 and suggestions:
                    # Get leaning info for suggestions
                    user_leanings = session.query(User_mgmt.id, User_mgmt.leaning).filter(
                        User_mgmt.id.in_(suggestions)
                    ).all()
                    leaning_map = {u.id: u.leaning for u in user_leanings}
                    agent_leaning = agent.leaning
                    
                    if agent_leaning:
                        # Score candidates by leaning match
                        leaning_scores = {}
                        for candidate in suggestions:
                            if leaning_map.get(candidate) == agent_leaning:
                                leaning_scores[candidate] = leaning_bias
                            else:
                                leaning_scores[candidate] = 1
                        
                        # Weighted random selection
                        weighted_suggestions = random.choices(
                            list(leaning_scores.keys()),
                            weights=list(leaning_scores.values()),
                            k=min(n_neighbors, len(leaning_scores))
                        )
                        suggestions = weighted_suggestions
                
                return suggestions[:n_neighbors]
                
        except Exception as e:
            self.logger.error(
                f"Error getting SQL follow suggestions: {e}",
                extra={"extra_data": {"error": str(e), "agent_id": agent_id, "mode": mode}}
            )
            # Fallback to simple random
            try:
                with Session(self.db.engine) as session:
                    candidates = session.query(User_mgmt.id).filter(
                        User_mgmt.id != agent_id
                    ).limit(n_neighbors * 2).all()
                    candidate_ids = [c.id for c in candidates]
                    random.shuffle(candidate_ids)
                    return candidate_ids[:n_neighbors]
            except:
                return []
    
    def _get_follow_suggestions_redis(
        self,
        agent_id: str,
        mode: str,
        n_neighbors: int,
        leaning_bias: int
    ) -> List[str]:
        """
        Get follow suggestions using Redis for better scalability with key-value storage.
        """
        try:
            # Get all user IDs from Redis
            user_ids_key = self.db._redis_key("user_mgmt", "ids")
            all_user_ids = list(self.db.redis_client.smembers(user_ids_key))
            
            if not all_user_ids:
                return []
            
            # Get agent info
            agent_key = self.db._redis_key("user_mgmt", agent_id)
            agent_data = self.db.redis_client.hgetall(agent_key)
            if not agent_data:
                return []
            
            # Get users agent is following
            # Check all follow records for this agent
            follow_pattern = self.db._redis_key("follow", "*")
            follow_keys = self.db.redis_client.keys(follow_pattern)
            
            following_ids = set()
            for key in follow_keys:
                follow_data = self.db.redis_client.hgetall(key)
                if follow_data.get("follower_id") == agent_id and follow_data.get("action") == "follow":
                    following_ids.add(follow_data.get("user_id"))
            
            # Get candidates (not following, not self)
            candidates = [uid for uid in all_user_ids if uid != agent_id and uid not in following_ids]
            
            if not candidates:
                return []
            
            if mode == "random":
                # Random selection
                random.shuffle(candidates)
                return candidates[:n_neighbors]
            
            elif mode == "preferential_attachment":
                # Count followers for each candidate
                follower_counts = {}
                for candidate in candidates:
                    count = 0
                    for key in follow_keys:
                        follow_data = self.db.redis_client.hgetall(key)
                        if follow_data.get("user_id") == candidate and follow_data.get("action") == "follow":
                            count += 1
                    follower_counts[candidate] = count
                
                # Sort by follower count
                sorted_candidates = sorted(follower_counts.items(), key=lambda x: x[1], reverse=True)
                return [uid for uid, _ in sorted_candidates[:n_neighbors]]
            
            elif mode in ["common_neighbors", "jaccard"]:
                # These modes require common neighbors analysis
                if not following_ids:
                    random.shuffle(candidates)
                    return candidates[:n_neighbors]
                
                # Find users that agent's friends also follow
                common_neighbor_counts = {}
                for candidate in candidates:
                    common_count = 0
                    # Check how many of agent's friends also follow this candidate
                    for friend_id in following_ids:
                        # Check if friend follows candidate
                        for key in follow_keys:
                            follow_data = self.db.redis_client.hgetall(key)
                            if (follow_data.get("follower_id") == friend_id and 
                                follow_data.get("user_id") == candidate and 
                                follow_data.get("action") == "follow"):
                                common_count += 1
                                break
                    common_neighbor_counts[candidate] = common_count
                
                # Sort by common neighbor count
                sorted_candidates = sorted(common_neighbor_counts.items(), key=lambda x: x[1], reverse=True)
                return [uid for uid, _ in sorted_candidates[:n_neighbors]]
            
            elif mode == "adamic_adar":
                # Adamic/Adar: sum of 1/log(degree) for common neighbors
                # Two-step approach: 1) Find common neighbors, 2) Calculate Adamic/Adar scores
                if not following_ids:
                    random.shuffle(candidates)
                    return candidates[:n_neighbors]
                
                # Step 1: Build candidate -> common neighbors mapping
                candidate_common_neighbors = {}
                for candidate in candidates:
                    common_neighbors = []
                    # Find which of agent's friends also follow this candidate
                    for friend_id in following_ids:
                        # Check if friend follows candidate
                        for key in follow_keys:
                            follow_data = self.db.redis_client.hgetall(key)
                            if (follow_data.get("follower_id") == friend_id and 
                                follow_data.get("user_id") == candidate and 
                                follow_data.get("action") == "follow"):
                                common_neighbors.append(friend_id)
                                break
                    if common_neighbors:
                        candidate_common_neighbors[candidate] = common_neighbors
                
                if not candidate_common_neighbors:
                    # No common neighbors found
                    random.shuffle(candidates)
                    return candidates[:n_neighbors]
                
                # Step 2: Calculate degree for each common neighbor
                neighbor_degrees = {}
                all_common_neighbors = set()
                for neighbors in candidate_common_neighbors.values():
                    all_common_neighbors.update(neighbors)
                
                for neighbor in all_common_neighbors:
                    # Count how many users this neighbor follows
                    degree = 0
                    for key in follow_keys:
                        follow_data = self.db.redis_client.hgetall(key)
                        if follow_data.get("follower_id") == neighbor and follow_data.get("action") == "follow":
                            degree += 1
                    neighbor_degrees[neighbor] = max(degree, 1)  # At least 1 to avoid division issues
                
                # Step 3: Calculate Adamic/Adar score for each candidate
                import math
                adamic_adar_scores = {}
                for candidate, neighbors in candidate_common_neighbors.items():
                    score = 0.0
                    for neighbor in neighbors:
                        degree = neighbor_degrees.get(neighbor, 1)
                        if degree > 1:  # Only count if degree > 1 (log(1) = 0)
                            score += 1.0 / math.log(degree)
                    adamic_adar_scores[candidate] = score
                
                # Sort by Adamic/Adar score (highest first)
                sorted_candidates = sorted(adamic_adar_scores.items(), key=lambda x: x[1], reverse=True)
                return [uid for uid, _ in sorted_candidates[:n_neighbors]]
            
            else:
                # Unknown mode, fallback to random
                random.shuffle(candidates)
                return candidates[:n_neighbors]
                
        except Exception as e:
            self.logger.error(
                f"Error getting Redis follow suggestions: {e}",
                extra={"extra_data": {"error": str(e), "agent_id": agent_id, "mode": mode}}
            )
            # Fallback to random from user_mgmt ids
            try:
                user_ids_key = self.db._redis_key("user_mgmt", "ids")
                all_user_ids = list(self.db.redis_client.smembers(user_ids_key))
                candidates = [uid for uid in all_user_ids if uid != agent_id]
                random.shuffle(candidates)
                return candidates[:n_neighbors]
            except:
                return []
