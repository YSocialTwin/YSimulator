"""
YServer - Orchestrator Server for YSimulator.

This module contains the Ray remote actor that orchestrates the simulation,
managing client registration, agent actions, and simulation state progression.
"""

import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import ray
from sqlalchemy import text

from YSimulator.YClient.classes.ray_models import SimulationInstruction


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
            limit: Number of posts to recommend (default: 5)
            visibility_rounds: Number of rounds (time slots) to look back for posts (default: 36)
            followers_ratio: Ratio of posts from followers vs others (default: 0.6)
            
        Returns:
            List[str]: List of post UUIDs recommended for the agent
        """
        try:
            # Calculate visibility threshold
            visibility = max(1, self.current_round_id - visibility_rounds)
            
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
                    valid_posts_with_data = []
                    for i, post_data in enumerate(posts_data):
                        if post_data:
                            post_round = post_data.get("round")
                            post_user_id = post_data.get("user_id")
                            # Check visibility and exclude own posts
                            if post_round and post_user_id != agent_id:
                                try:
                                    if int(post_round) >= visibility:
                                        valid_posts_with_data.append({
                                            'id': all_post_ids[i],
                                            'round': int(post_round),
                                            'reaction_count': int(post_data.get("reaction_count", 0) or 0)
                                        })
                                except (ValueError, TypeError):
                                    continue
                else:
                    valid_posts_with_data = []
                
                # Apply mode-specific ordering
                if mode == "rchrono":
                    # Redis recent list is already in reverse chronological order (newest first)
                    # Just take the first 'limit' items
                    post_ids = [p['id'] for p in valid_posts_with_data[:limit]]
                    
                elif mode == "rchrono_popularity":
                    # Sort by round desc, then by reaction_count desc
                    sorted_posts = sorted(valid_posts_with_data, 
                                        key=lambda x: (x['round'], x['reaction_count']), 
                                        reverse=True)
                    post_ids = [p['id'] for p in sorted_posts[:limit]]
                    
                elif mode in ["rchrono_followers", "rchrono_followers_popularity", "rchrono_comments"]:
                    # For follower-based modes in Redis, fallback to reverse chronological
                    # Complex joins not easily supported in Redis
                    self.logger.info(f"Mode {mode} not fully supported in Redis, using rchrono fallback")
                    post_ids = [p['id'] for p in valid_posts_with_data[:limit]]
                    
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
                
                return post_ids
                
            else:
                # Use SQL database for recommendations
                with self.db.engine.begin() as connection:
                    
                    if mode == "rchrono":
                        # Reverse chronological: newest posts first
                        query = text("""
                            SELECT id FROM post 
                            WHERE round >= :visibility AND user_id != :agent_id
                            ORDER BY round DESC, id DESC
                            LIMIT :limit
                        """)
                        result = connection.execute(query, {
                            "visibility": visibility,
                            "agent_id": agent_id,
                            "limit": limit
                        })
                        post_ids = [row[0] for row in result]
                        
                    elif mode == "rchrono_popularity":
                        # Reverse chronological with popularity (reaction count)
                        query = text("""
                            SELECT p.id 
                            FROM post p
                            LEFT JOIN (
                                SELECT post_id, COUNT(*) as reaction_count
                                FROM reaction
                                GROUP BY post_id
                            ) r ON p.id = r.post_id
                            WHERE p.round >= :visibility AND p.user_id != :agent_id
                            ORDER BY p.round DESC, COALESCE(r.reaction_count, 0) DESC
                            LIMIT :limit
                        """)
                        result = connection.execute(query, {
                            "visibility": visibility,
                            "agent_id": agent_id,
                            "limit": limit
                        })
                        post_ids = [row[0] for row in result]
                        
                    elif mode == "rchrono_followers":
                        # Prioritize posts from followed users
                        follower_posts_limit = int(limit * followers_ratio)
                        additional_posts_limit = limit - follower_posts_limit
                        
                        # Get posts from followed users
                        query_followers = text("""
                            SELECT DISTINCT p.id 
                            FROM post p
                            INNER JOIN follow f ON p.user_id = f.follower_id
                            WHERE f.user_id = :agent_id 
                                AND f.action = 'follow'
                                AND p.round >= :visibility
                                AND p.user_id != :agent_id
                            ORDER BY p.round DESC
                            LIMIT :follower_limit
                        """)
                        result = connection.execute(query_followers, {
                            "agent_id": agent_id,
                            "visibility": visibility,
                            "follower_limit": follower_posts_limit
                        })
                        post_ids = [row[0] for row in result]
                        
                        # If we need more posts, get additional ones
                        if len(post_ids) < limit and additional_posts_limit > 0:
                            query_additional = text("""
                                SELECT id FROM post
                                WHERE round >= :visibility 
                                    AND user_id != :agent_id
                                    AND id NOT IN :existing_ids
                                ORDER BY round DESC
                                LIMIT :additional_limit
                            """)
                            # Handle empty list case for SQL IN clause
                            existing_ids = tuple(post_ids) if post_ids else ('',)
                            result = connection.execute(query_additional, {
                                "visibility": visibility,
                                "agent_id": agent_id,
                                "existing_ids": existing_ids,
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
                            INNER JOIN follow f ON p.user_id = f.follower_id
                            LEFT JOIN (
                                SELECT post_id, COUNT(*) as reaction_count
                                FROM reaction
                                GROUP BY post_id
                            ) r ON p.id = r.post_id
                            WHERE f.user_id = :agent_id 
                                AND f.action = 'follow'
                                AND p.round >= :visibility
                                AND p.user_id != :agent_id
                            ORDER BY p.round DESC, COALESCE(r.reaction_count, 0) DESC
                            LIMIT :follower_limit
                        """)
                        result = connection.execute(query_followers, {
                            "agent_id": agent_id,
                            "visibility": visibility,
                            "follower_limit": follower_posts_limit
                        })
                        post_ids = [row[0] for row in result]
                        
                        if len(post_ids) < limit and additional_posts_limit > 0:
                            existing_ids = tuple(post_ids) if post_ids else ('',)
                            query_additional = text("""
                                SELECT p.id 
                                FROM post p
                                LEFT JOIN (
                                    SELECT post_id, COUNT(*) as reaction_count
                                    FROM reaction
                                    GROUP BY post_id
                                ) r ON p.id = r.post_id
                                WHERE p.round >= :visibility 
                                    AND p.user_id != :agent_id
                                    AND p.id NOT IN :existing_ids
                                ORDER BY p.round DESC, COALESCE(r.reaction_count, 0) DESC
                                LIMIT :additional_limit
                            """)
                            result = connection.execute(query_additional, {
                                "visibility": visibility,
                                "agent_id": agent_id,
                                "existing_ids": existing_ids,
                                "additional_limit": additional_posts_limit
                            })
                            post_ids.extend([row[0] for row in result])
                            
                    elif mode == "rchrono_comments":
                        # Prioritize posts with more comments (thread activity)
                        query = text("""
                            SELECT p.id, COUNT(c.id) as comment_count
                            FROM post p
                            LEFT JOIN post c ON p.id = c.thread_id AND c.comment_to IS NOT NULL
                            WHERE p.round >= :visibility 
                                AND p.user_id != :agent_id
                                AND p.comment_to IS NULL
                            GROUP BY p.id
                            ORDER BY comment_count DESC, p.round DESC
                            LIMIT :limit
                        """)
                        result = connection.execute(query, {
                            "visibility": visibility,
                            "agent_id": agent_id,
                            "limit": limit
                        })
                        post_ids = [row[0] for row in result]
                        
                    else:
                        # Random ordering (default)
                        # Note: RANDOM() works for SQLite and PostgreSQL
                        # For MySQL, use RAND() instead
                        query = text("""
                            SELECT id FROM post 
                            WHERE round >= :visibility AND user_id != :agent_id
                            ORDER BY RANDOM()
                            LIMIT :limit
                        """)
                        result = connection.execute(query, {
                            "visibility": visibility,
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
