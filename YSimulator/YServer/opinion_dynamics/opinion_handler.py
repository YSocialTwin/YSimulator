"""
Opinion handler for managing agent opinions.

Handles opinion existence checks, updates, and neighbor opinion retrieval.
"""

import logging
from typing import Dict, List, Optional


class OpinionHandler:
    """
    Handles opinion dynamics for agents in the simulation.
    
    Manages opinion creation, updates, and retrieval, supporting
    both bounded confidence models and LLM-based opinion inference.
    """
    
    def __init__(
        self,
        db_adapter,
        simulation_config: dict,
        agent_profiles_cache: dict,
        current_round_id_getter: callable,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize opinion handler.
        
        Args:
            db_adapter: Database adapter for opinion storage/retrieval
            simulation_config: Simulation configuration dict
            agent_profiles_cache: Cache of agent profiles for opinion lookup
            current_round_id_getter: Callable that returns current round ID
            logger: Logger instance
        """
        self.db = db_adapter
        self.simulation_config = simulation_config
        self.agent_profiles_cache = agent_profiles_cache
        self._get_current_round_id = current_round_id_getter
        self.logger = logger or logging.getLogger(__name__)
        
        # Get opinion dynamics configuration
        self.opinion_config = simulation_config.get("opinion_dynamics", {})
        self.enabled = self.opinion_config.get("enabled", False)
    
    def ensure_agent_opinion_exists(
        self,
        agent_id: str,
        topic_id: str,
        topic_name: str,
        article_content: str = None
    ) -> None:
        """
        Ensure an agent has an opinion recorded for a topic.
        
        This is a safety fallback that creates opinions if they don't exist.
        For page agents, the client should have already inferred opinions via LLM
        before submitting the POST action. This method just provides defaults.
        
        For regular agents: Use cached profile opinion or neutral (0.5) as fallback.
        For page agents: Use neutral (0.5) as placeholder (client should set opinion first).
        
        Only executes when opinion dynamics is enabled in simulation config.
        
        NOTE: Server does NOT call LLM service. All LLM interactions happen on client side.
        
        Args:
            agent_id: Agent UUID
            topic_id: Topic UUID (from interests table)
            topic_name: Topic name for looking up in cached profile
            article_content: Unused (kept for backwards compatibility)
        """
        # Only enforce this constraint when opinion dynamics is enabled
        if not self.enabled:
            return  # Opinion dynamics disabled, no need to ensure opinions exist
        
        # Check if agent already has an opinion on this topic
        existing_opinion = self.db.get_latest_agent_opinion(agent_id, topic_id)
        if existing_opinion is not None:
            return  # Opinion already exists
        
        # Agent doesn't have opinion - need to create one as fallback
        cached_profile = self.agent_profiles_cache.get(agent_id)
        is_page_agent = cached_profile and cached_profile.is_page == 1
        
        opinion_value = None
        
        if is_page_agent:
            # Page agent: Client should have already set opinion via LLM/random
            # This is just a fallback - use neutral placeholder
            opinion_value = 0.5
            self.logger.warning(
                f"Page agent {agent_id}: no opinion found for topic '{topic_name}'. "
                f"Using neutral fallback (0.5). Client should have set opinion first."
            )
        else:
            # Regular agent: try to get from cached profile
            if cached_profile and cached_profile.opinions:
                # Try exact match first
                opinion_value = cached_profile.opinions.get(topic_name)
                # If not found, try case-insensitive match
                if opinion_value is None:
                    for key, value in cached_profile.opinions.items():
                        if key.lower() == topic_name.lower():
                            opinion_value = value
                            break
                
                if opinion_value is not None:
                    self.logger.info(
                        f"Regular agent {agent_id}: using initial opinion {opinion_value} from profile for topic '{topic_name}'"
                    )
            
            # Default to neutral opinion if not found in profile
            if opinion_value is None:
                opinion_value = 0.5
                self.logger.info(
                    f"Regular agent {agent_id}: creating default neutral opinion {opinion_value} for topic '{topic_name}'"
                )
        
        # Store the opinion
        current_round_id = self._get_current_round_id()
        self.db.add_agent_opinion(
            agent_id=agent_id,
            round_id=current_round_id,
            topic_id=topic_id,
            opinion=opinion_value,
            id_interacted_with=None,
            id_post=None,
        )
    
    def get_latest_opinion(self, agent_id: str, topic_id: str) -> Optional[float]:
        """
        Get the latest opinion value for an agent on a topic.
        
        Args:
            agent_id: Agent UUID
            topic_id: Topic UUID
            
        Returns:
            Latest opinion value or None if not found
        """
        return self.db.get_latest_agent_opinion(agent_id, topic_id)
    
    def add_opinion(
        self,
        agent_id: str,
        topic_id: str,
        opinion: float,
        id_interacted_with: Optional[str] = None,
        id_post: Optional[str] = None,
    ) -> bool:
        """
        Add an agent opinion record to the database.
        
        Args:
            agent_id: Agent UUID
            topic_id: Topic UUID
            opinion: Opinion value in [0, 1]
            id_interacted_with: Optional UUID of agent interacted with
            id_post: Optional UUID of post interacted with
            
        Returns:
            True if successful, False otherwise
        """
        current_round_id = self._get_current_round_id()
        return self.db.add_agent_opinion(
            agent_id, current_round_id, topic_id, opinion, id_interacted_with, id_post
        )
    
    def get_neighbors_opinions(self, agent_id: str, topic_id: str) -> List[float]:
        """
        Get the opinions of an agent's neighbors (followees) on a specific topic.
        
        This method retrieves the latest opinions of all users that the agent follows
        on the specified topic. Used for LLM-based opinion dynamics with evaluation_scope="neighbors".
        
        Args:
            agent_id: Agent UUID
            topic_id: Topic UUID
            
        Returns:
            List of opinion values (floats in [0, 1]) from the agent's neighbors
        """
        try:
            if self.db.use_redis:
                return self._get_neighbors_opinions_redis(agent_id, topic_id)
            else:
                return self._get_neighbors_opinions_sql(agent_id, topic_id)
        except Exception as e:
            self.logger.error(
                f"Error getting neighbors opinions: {e}",
                extra={"extra_data": {"error": str(e), "agent_id": agent_id, "topic_id": topic_id}},
            )
            return []
    
    def _get_neighbors_opinions_redis(self, agent_id: str, topic_id: str) -> List[float]:
        """Get neighbors opinions using Redis backend."""
        # Redis implementation: hybrid approach
        # Step 1: Get followees from Redis follow keys
        follow_pattern = self.db.get_redis_key_pattern("follow", "*")
        # Note: Using KEYS here for consistency with follow_recsys_redis.py
        # For large-scale production deployments, consider using SCAN instead
        follow_keys = self.db.redis_client.keys(follow_pattern)
        
        # Encode agent_id once for efficiency
        agent_id_bytes = agent_id.encode()
        
        followee_ids = set()
        for key in follow_keys:
            follow_data = self.db.redis_client.hgetall(key)
            # Check if this is a follow relationship for the agent
            if (
                follow_data.get(b"follower_id") == agent_id_bytes
                and follow_data.get(b"action") == b"follow"
            ):
                user_id = follow_data.get(b"user_id")
                if user_id:
                    followee_ids.add(user_id.decode())
        
        if not followee_ids:
            return []
        
        # Step 2: Get opinions from Redis for each followee
        opinions = []
        for followee_id in followee_ids:
            opinion = self.db.get_latest_agent_opinion(followee_id, topic_id)
            if opinion is not None:
                opinions.append(opinion)
        
        return opinions
    
    def _get_neighbors_opinions_sql(self, agent_id: str, topic_id: str) -> List[float]:
        """Get neighbors opinions using SQL backend."""
        from sqlalchemy.orm import Session
        from YSimulator.YServer.classes.models import Follow
        
        with Session(self.db.engine) as session:
            # Get list of user_ids that agent follows (where agent is the follower and action='follow')
            followees_query = (
                session.query(Follow.user_id)
                .filter(Follow.follower_id == agent_id, Follow.action == "follow")
                .all()
            )
            
            followee_ids = [row[0] for row in followees_query]
            
            if not followee_ids:
                return []
            
            # Get opinions of each followee on this topic
            opinions = []
            for followee_id in followee_ids:
                opinion = self.db.get_latest_agent_opinion(followee_id, topic_id)
                if opinion is not None:
                    opinions.append(opinion)
            
            return opinions
