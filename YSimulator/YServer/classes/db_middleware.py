"""
Database middleware for YSimulator.

This module provides a middleware layer that can use either Redis (if available)
or SQLite as the database backend. The middleware abstracts database operations
to allow seamless switching between backends.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from YSimulator.YServer.classes.models import Base, Reaction, Post, User_mgmt, Round


class DatabaseMiddleware:
    """
    Database middleware that supports multiple SQLAlchemy-compatible backends.

    Supports SQLite, PostgreSQL, and MySQL as database backends.
    If Redis is available and configured, it will be used as a high-performance cache.
    """

    def __init__(
        self,
        db_config: Dict[str, Any],
        config_path: str = ".",
        redis_config: Optional[Dict[str, Any]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize the database middleware.

        Args:
            db_config: Database configuration dict with 'type' and backend-specific settings
            config_path: Path to configuration directory (for SQLite database file)
            redis_config: Redis configuration dict with keys: host, port, db, password, sliding_window_days (optional)
            logger: Logger instance for logging operations
        """
        from pathlib import Path

        self.logger = logger or logging.getLogger(__name__)
        self.use_redis = False
        self.redis_client = None
        self.redis_sliding_window_days = 2  # Default: keep last 2 days in Redis
        self.db_type = db_config.get("type", "sqlite").lower()
        self.config_path = Path(config_path)

        # Try to initialize Redis if explicitly configured with enabled=true and host specified
        if redis_config and isinstance(redis_config, dict) and redis_config.get("enabled", False):
            # Get sliding window configuration (default to 2 days)
            self.redis_sliding_window_days = redis_config.get("sliding_window_days", 2)

            # Validate that Redis host is provided
            if not redis_config.get("host"):
                self.logger.info(
                    "Redis is enabled but no host specified in config, using SQL database only"
                )
            elif not REDIS_AVAILABLE:
                self.logger.warning(
                    "Redis is enabled in config but redis module is not installed. "
                    "Install with: pip install redis"
                )
            else:
                try:
                    self.redis_client = redis.Redis(
                        host=redis_config.get("host"),
                        port=redis_config.get("port", 6379),
                        db=redis_config.get("db", 0),
                        password=redis_config.get("password"),
                        decode_responses=True,
                    )
                    # Test connection
                    self.redis_client.ping()
                    self.use_redis = True
                    self.logger.info(
                        "Redis connection established",
                        extra={
                            "extra_data": {
                                "host": redis_config.get("host"),
                                "port": redis_config.get("port"),
                            }
                        },
                    )
                except Exception as e:
                    self.logger.warning(
                        f"Redis connection failed, falling back to SQL database: {e}",
                        extra={"extra_data": {"error": str(e)}},
                    )
                    self.use_redis = False
                    self.redis_client = None

        # Build SQLAlchemy connection string based on database type
        connection_string = self._build_connection_string(db_config)

        # Initialize SQL database backend
        self.engine = create_engine(connection_string)
        Base.metadata.create_all(self.engine)
        
        # Initialize round cache for performance
        self.round_cache = {}  # Cache: (day, hour) -> round_id
        
        self.logger.info(
            "SQL database initialized",
            extra={
                "extra_data": {
                    "db_type": self.db_type,
                    "redis_enabled": self.use_redis,
                }
            },
        )

    @staticmethod
    def _is_empty_or_default(value) -> bool:
        """
        Check if a value is empty or a default placeholder (-1, '-1', '', None).
        
        This helper handles the database's use of -1 as a default value for foreign keys
        that can be either integers or strings depending on context.
        
        Args:
            value: The value to check
            
        Returns:
            bool: True if the value should be considered empty/default
        """
        return not value or value == -1 or value == "-1" or value == ""

    def _build_connection_string(self, db_config: Dict[str, Any]) -> str:
        """
        Build SQLAlchemy connection string based on database configuration.

        Args:
            db_config: Database configuration dict

        Returns:
            SQLAlchemy connection string

        Raises:
            ValueError: If database type is not supported or required parameters are missing
        """
        from urllib.parse import quote_plus

        db_type = db_config.get("type", "sqlite").lower()

        if db_type == "sqlite":
            sqlite_config = db_config.get("sqlite", {})
            filename = sqlite_config.get("filename", "simulation.db")
            # Create database file in config directory
            db_path = self.config_path / filename
            return f"sqlite:///{db_path}"

        elif db_type == "postgresql":
            pg_config = db_config.get("postgresql", {})
            host = pg_config.get("host", "localhost")
            port = pg_config.get("port", 5432)
            database = pg_config.get("database")
            username = pg_config.get("username")
            password = pg_config.get("password")

            if not all([database, username]):
                raise ValueError(
                    "PostgreSQL requires 'database' and 'username' in configuration"
                )

            # URL encode password to handle special characters
            if password:
                encoded_password = quote_plus(password)
                return f"postgresql://{username}:{encoded_password}@{host}:{port}/{database}"
            else:
                return f"postgresql://{username}@{host}:{port}/{database}"

        elif db_type == "mysql":
            mysql_config = db_config.get("mysql", {})
            host = mysql_config.get("host", "localhost")
            port = mysql_config.get("port", 3306)
            database = mysql_config.get("database")
            username = mysql_config.get("username")
            password = mysql_config.get("password")

            if not all([database, username]):
                raise ValueError("MySQL requires 'database' and 'username' in configuration")

            # URL encode password to handle special characters
            if password:
                encoded_password = quote_plus(password)
                return f"mysql+pymysql://{username}:{encoded_password}@{host}:{port}/{database}"
            else:
                return f"mysql+pymysql://{username}@{host}:{port}/{database}"

        else:
            raise ValueError(
                f"Unsupported database type: {db_type}. Supported types: sqlite, postgresql, mysql"
            )

    def _redis_key(self, table: str, id: Any = None) -> str:
        """Generate Redis key for a table and optional ID."""
        if id is not None:
            return f"ysim:{table}:{id}"
        return f"ysim:{table}"

    def register_user(self, user_data: Dict[str, Any]) -> bool:
        """
        Register a user in the database.

        Args:
            user_data: Dictionary containing user data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if self.use_redis:
                # Store in Redis as hash
                user_id = user_data["id"]
                key = self._redis_key("user_mgmt", user_id)

                # Check if user already exists
                if self.redis_client.exists(key):
                    return False

                # Filter out None values for Redis (Redis cannot store None)
                redis_data = {k: v for k, v in user_data.items() if v is not None}
                
                # Store user data
                self.redis_client.hset(key, mapping=redis_data)
                # Add to user set
                self.redis_client.sadd(self._redis_key("user_mgmt", "ids"), user_id)
                return True
            else:
                # Store in SQLite
                session = Session(self.engine)
                try:
                    existing = session.query(User_mgmt).filter_by(id=user_data["id"]).first()
                    if existing:
                        return False

                    user = User_mgmt(**user_data)
                    session.add(user)
                    session.commit()
                    return True
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(
                f"Error registering user: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get user by ID.

        Args:
            user_id: User ID

        Returns:
            Dict with user data or None if not found
        """
        try:
            if self.use_redis:
                key = self._redis_key("user_mgmt", user_id)
                if not self.redis_client.exists(key):
                    return None
                return self.redis_client.hgetall(key)
            else:
                session = Session(self.engine)
                try:
                    user = session.query(User_mgmt).filter_by(id=user_id).first()
                    if not user:
                        return None
                    # Convert to dict with proper type handling
                    return {
                        c.name: (
                            str(getattr(user, c.name))
                            if getattr(user, c.name) is not None
                            else None
                        )
                        for c in user.__table__.columns
                    }
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(f"Error getting user: {e}", extra={"extra_data": {"error": str(e)}})
            return None

    def add_post(self, post_data: Dict[str, Any]) -> Optional[str]:
        """
        Add a post to the database.

        Args:
            post_data: Dictionary containing post data

        Returns:
            str: Post UUID if successful, None otherwise
        """
        try:
            # Generate UUID for post
            post_id = str(uuid.uuid4())
            post_data["id"] = post_id
            
            # Set thread_id logic:
            # - If comment_to is set and not -1 (comment), thread_id should already be set by caller
            # - Otherwise (new post or share), set thread_id to post_id
            comment_to = post_data.get("comment_to")
            if self._is_empty_or_default(comment_to):
                # New post or share - create new thread
                post_data["thread_id"] = post_id
            # If comment_to is set to a valid value, thread_id should already be set by the caller

            if self.use_redis:
                # Store post
                key = self._redis_key("posts", post_id)
                # Filter out None values for Redis (Redis cannot store None)
                redis_data = {k: v for k, v in post_data.items() if v is not None}
                self.redis_client.hset(key, mapping=redis_data)

                # Add to posts list
                self.redis_client.lpush(self._redis_key("posts", "recent"), post_id)
                # Keep only last 50
                self.redis_client.ltrim(self._redis_key("posts", "recent"), 0, 49)

                return post_id
            else:
                session = Session(self.engine)
                try:
                    post = Post(**post_data)
                    session.add(post)
                    session.commit()
                    return post_id
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(f"Error adding post: {e}", extra={"extra_data": {"error": str(e)}})
            return None

    def add_interaction(self, interaction_data: Dict[str, Any]) -> bool:
        """
        Add an interaction to the database.

        Args:
            interaction_data: Dictionary containing interaction data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Generate UUID for interaction
            interaction_id = str(uuid.uuid4())
            interaction_data["id"] = interaction_id

            if self.use_redis:
                # Store interaction
                key = self._redis_key("interactions", interaction_id)
                # Filter out None values for Redis (Redis cannot store None)
                redis_data = {k: v for k, v in interaction_data.items() if v is not None}
                self.redis_client.hset(key, mapping=redis_data)
                return True
            else:
                session = Session(self.engine)
                try:
                    interaction = Reaction(**interaction_data)
                    session.add(interaction)
                    session.commit()
                    return True
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(
                f"Error adding interaction: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return False

    def get_post(self, post_id: str) -> Optional[Dict[str, Any]]:
        """
        Get post data by ID.
        
        Args:
            post_id: Post UUID
            
        Returns:
            dict: Post data if found, None otherwise
        """
        try:
            if self.use_redis:
                key = self._redis_key("posts", post_id)
                post_data = self.redis_client.hgetall(key)
                return post_data if post_data else None
            else:
                session = Session(self.engine)
                try:
                    post = session.query(Post).filter(Post.id == post_id).first()
                    if post:
                        return {
                            "id": post.id,
                            "thread_id": post.thread_id,
                            "news_id": post.news_id,
                            "comment_to": post.comment_to,
                            "shared_from": post.shared_from,
                            "user_id": post.user_id,
                            "tweet": post.tweet,
                            "round": post.round,
                        }
                    return None
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting post: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return None

    def get_recent_posts(self, limit: int = 50) -> List[str]:
        """
        Get recent post IDs.

        Args:
            limit: Maximum number of posts to return

        Returns:
            List of post UUIDs (as strings)
        """
        try:
            if self.use_redis:
                post_ids = self.redis_client.lrange(
                    self._redis_key("posts", "recent"), 0, limit - 1
                )
                return [str(pid) for pid in post_ids]
            else:
                session = Session(self.engine)
                try:
                    posts = (
                        session.query(Post).order_by(Post.id.desc()).limit(limit).all()
                    )
                    return [post.id for post in posts]
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(
                f"Error getting recent posts: {e}", extra={"extra_data": {"error": str(e)}}
            )
            return []

    def consolidate_redis_to_sqlite(self, day: int) -> dict:
        """
        Consolidate Redis data to SQLite at the end of a simulation day.

        This method transfers all posts and interactions from Redis to SQLite.
        It then removes data older than the sliding window from Redis to manage memory.

        Args:
            day: The simulation day being consolidated

        Returns:
            dict: Summary with counts of posts and interactions transferred and removed
        """
        if not self.use_redis:
            return {
                "posts": 0,
                "interactions": 0,
                "removed_posts": 0,
                "removed_interactions": 0,
                "message": "Not using Redis",
            }

        try:
            session = Session(self.engine)
            posts_count = 0
            interactions_count = 0
            removed_posts_count = 0
            removed_interactions_count = 0

            try:
                # Get all post keys
                post_pattern = self._redis_key("posts", "*")
                post_keys = [
                    k
                    for k in self.redis_client.keys(post_pattern)
                    if not k.endswith(":recent") and not k.endswith(":counter")
                ]

                # Transfer all posts to SQL
                for key in post_keys:
                    post_data = self.redis_client.hgetall(key)
                    if post_data and "id" in post_data:
                        # Check if post already exists in SQLite
                        existing = session.query(Post).filter_by(id=post_data["id"]).first()
                        if not existing:
                            post = Post(
                                id=post_data["id"],
                                tweet=post_data.get("tweet", ""),
                                user_id=str(post_data.get("user_id", "")),
                                round=str(post_data.get("round", "")),
                            )
                            session.add(post)
                            posts_count += 1

                # Get all interaction keys
                interaction_pattern = self._redis_key("interactions", "*")
                interaction_keys = [
                    k
                    for k in self.redis_client.keys(interaction_pattern)
                    if not k.endswith(":counter")
                ]

                # Transfer all interactions to SQL
                for key in interaction_keys:
                    interaction_data = self.redis_client.hgetall(key)
                    if interaction_data and "id" in interaction_data:
                        # Check if interaction already exists in SQLite
                        existing = (
                            session.query(Reaction)
                            .filter_by(id=interaction_data["id"])
                            .first()
                        )
                        if not existing:
                            interaction = Reaction(
                                id=interaction_data["id"],
                                user_id=str(interaction_data.get("user_id", "")),
                                post_id=interaction_data.get("post_id", ""),
                                type=interaction_data.get("type", ""),
                                round=str(interaction_data.get("round", "")),
                            )
                            session.add(interaction)
                            interactions_count += 1

                # Commit all to SQLite
                session.commit()

                # Keep data in Redis for fast queries during simulation
                # SQL serves as permanent storage, Redis as hot cache
                removed_posts_count = 0
                removed_interactions_count = 0

                self.logger.info(
                    f"Consolidated Redis data for day {day}",
                    extra={
                        "extra_data": {
                            "day": day,
                            "posts_saved": posts_count,
                            "interactions_saved": interactions_count,
                        }
                    },
                )

                return {
                    "posts": posts_count,
                    "interactions": interactions_count,
                    "removed_posts": removed_posts_count,
                    "removed_interactions": removed_interactions_count,
                    "message": "Consolidation successful",
                }

            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()

        except Exception as e:
            self.logger.error(
                f"Error consolidating Redis to SQLite: {e}",
                extra={"extra_data": {"error": str(e), "day": day}},
            )
            return {
                "posts": 0,
                "interactions": 0,
                "removed_posts": 0,
                "removed_interactions": 0,
                "message": f"Consolidation failed: {str(e)}",
            }

    def get_or_create_round(self, day: int, hour: int) -> str:
        """
        Get or create a Round entry for the given day and hour.
        
        This method ensures that each (day, hour) combination has exactly one Round
        record in the database, which is used as a foreign key reference by posts,
        reactions, and other temporal entities.
        
        Args:
            day: Simulation day number
            hour: Hour/slot within the day (typically 1-24)
            
        Returns:
            str: UUID of the Round record
        """
        # Check cache first for performance
        cache_key = (day, hour)
        if cache_key in self.round_cache:
            return self.round_cache[cache_key]
        
        # Query or create in database
        session = Session(self.engine)
        try:
            # Try to find existing round
            round_obj = session.query(Round).filter_by(day=day, hour=hour).first()
            
            if not round_obj:
                # Create new round
                round_id = str(uuid.uuid4())
                round_obj = Round(id=round_id, day=day, hour=hour)
                session.add(round_obj)
                session.commit()
                
                self.logger.debug(
                    f"Created new Round entry",
                    extra={
                        "extra_data": {
                            "round_id": round_id,
                            "day": day,
                            "hour": hour,
                        }
                    },
                )
            
            # Cache the result
            self.round_cache[cache_key] = round_obj.id
            return round_obj.id
            
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error getting/creating round: {e}",
                extra={"extra_data": {"error": str(e), "day": day, "hour": hour}},
            )
            raise
        finally:
            session.close()

    def get_all_users(self) -> List[Dict[str, Any]]:
        """
        Get all registered users from the database.
        
        Returns:
            List[Dict]: List of user dictionaries with id, username, and archetype
        """
        from YSimulator.YServer.classes.models import User_mgmt
        
        session = Session(self.engine)
        try:
            users = session.query(User_mgmt).all()
            
            result = []
            for user in users:
                result.append({
                    "id": user.id,
                    "username": user.username,
                    "archetype": user.archetype,
                })
            
            return result
            
        except Exception as e:
            self.logger.error(
                f"Error getting all users: {e}",
                extra={"extra_data": {"error": str(e)}}
            )
            return []
        finally:
            session.close()

    def update_user_archetype(self, user_id: str, new_archetype: str) -> bool:
        """
        Update the archetype of a user in the database.
        
        Args:
            user_id: User ID (UUID string)
            new_archetype: New archetype value
            
        Returns:
            bool: True if update successful, False otherwise
        """
        from YSimulator.YServer.classes.models import User_mgmt
        
        session = Session(self.engine)
        try:
            user = session.query(User_mgmt).filter(User_mgmt.id == user_id).first()
            
            if user:
                user.archetype = new_archetype
                session.commit()
                return True
            else:
                self.logger.warning(
                    f"User {user_id} not found for archetype update"
                )
                return False
                
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error updating user archetype: {e}",
                extra={"extra_data": {"error": str(e), "user_id": user_id, "new_archetype": new_archetype}}
            )
            return False
        finally:
            session.close()

    def add_website(self, website_data: Dict[str, Any]) -> Optional[str]:
        """
        Add a website (news source) to the database.
        
        Args:
            website_data (dict): Website information with keys:
                - id: Website UUID
                - name: Website name
                - rss: RSS feed URL
                - leaning: Political leaning (optional)
                - category: Content category (optional)
                - country: Country code (optional)
                - language: Language code (optional)
                - last_fetched: Last fetch timestamp (optional)
                
        Returns:
            str: Website ID if successful, None otherwise
        """
        from YSimulator.YServer.classes.models import Website
        import uuid
        
        session = Session(self.engine)
        try:
            # Generate UUID if not provided
            website_id = website_data.get("id", str(uuid.uuid4()))
            
            # Check if website already exists by RSS URL
            existing = session.query(Website).filter(Website.rss == website_data.get("rss")).first()
            if existing:
                return existing.id
            
            # Create new website
            website = Website(
                id=website_id,
                name=website_data.get("name"),
                rss=website_data.get("rss"),
                leaning=website_data.get("leaning"),
                category=website_data.get("category"),
                country=website_data.get("country"),
                language=website_data.get("language"),
                last_fetched=website_data.get("last_fetched", str(uuid.uuid4()))
            )
            
            session.add(website)
            session.commit()
            
            # Also cache in Redis if enabled
            if self.use_redis:
                redis_key = self._redis_key("websites", website_id)
                self.redis_client.hset(redis_key, mapping={
                    "id": website_id,
                    "name": website_data.get("name", ""),
                    "rss": website_data.get("rss", ""),
                    "category": website_data.get("category", ""),
                    "language": website_data.get("language", "")
                })
            
            return website_id
            
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error adding website: {e}",
                extra={"extra_data": {"error": str(e), "website_data": website_data}}
            )
            return None
        finally:
            session.close()

    def add_article(self, article_data: Dict[str, Any]) -> Optional[str]:
        """
        Add a news article to the database.
        
        Ensures the related website exists before creating the article.
        If website_id is provided but doesn't exist, returns None.
        If rss_url is provided instead of website_id, looks up or creates the website.
        
        Args:
            article_data (dict): Article information with keys:
                - id: Article UUID (optional, will be generated)
                - title: Article title
                - summary: Article summary/description
                - website_id: Reference to website (UUID) - required if rss_url not provided
                - rss_url: RSS feed URL - used to lookup/create website if website_id not provided
                - website_name: Website name - used when creating website from rss_url
                - link: Article URL
                - fetched_on: Fetch timestamp (UUID format)
                
        Returns:
            str: Article ID if successful, None otherwise
        """
        from YSimulator.YServer.classes.models import Article, Website
        import uuid
        
        session = Session(self.engine)
        try:
            # Get or ensure website exists
            website_id = article_data.get("website_id")
            
            # If no website_id provided, try to get it from rss_url
            if not website_id:
                rss_url = article_data.get("rss_url")
                if rss_url:
                    # Look up website by RSS URL
                    website = session.query(Website).filter(Website.rss == rss_url).first()
                    if website:
                        website_id = website.id
                    else:
                        # Create new website
                        website_id = str(uuid.uuid4())
                        new_website = Website(
                            id=website_id,
                            name=article_data.get("website_name", "Unknown"),
                            rss=rss_url,
                            category=article_data.get("category"),
                            language=article_data.get("language"),
                            country=article_data.get("country"),
                            leaning=article_data.get("leaning"),
                            last_fetched=str(uuid.uuid4())
                        )
                        session.add(new_website)
                        session.flush()  # Ensure website is created before article
            
            # Verify website exists
            if not website_id:
                self.logger.error("Cannot add article: no website_id or rss_url provided")
                return None
                
            website_exists = session.query(Website).filter(Website.id == website_id).first()
            if not website_exists:
                self.logger.error(
                    f"Cannot add article: website {website_id} does not exist",
                    extra={"extra_data": {"website_id": website_id}}
                )
                return None
            
            # Generate UUID if not provided
            article_id = article_data.get("id", str(uuid.uuid4()))
            
            # Check if article already exists by link
            existing = session.query(Article).filter(Article.link == article_data.get("link")).first()
            if existing:
                return existing.id
            
            # Create new article
            article = Article(
                id=article_id,
                title=article_data.get("title"),
                summary=article_data.get("summary"),
                website_id=website_id,
                link=article_data.get("link"),
                fetched_on=article_data.get("fetched_on", str(uuid.uuid4()))
            )
            
            session.add(article)
            session.commit()
            
            # Also cache in Redis if enabled
            if self.use_redis:
                redis_key = self._redis_key("articles", article_id)
                self.redis_client.hset(redis_key, mapping={
                    "id": article_id,
                    "title": article_data.get("title", ""),
                    "summary": article_data.get("summary", "")[:200],  # Truncate for Redis
                    "website_id": website_id,
                    "link": article_data.get("link", "")
                })
            
            return article_id
            
        except Exception as e:
            session.rollback()
            self.logger.error(
                f"Error adding article: {e}",
                extra={"extra_data": {"error": str(e), "article_data": article_data}}
            )
            return None
        finally:
            session.close()

    def get_website_by_rss(self, rss_url: str) -> Optional[Dict[str, Any]]:
        """
        Get website by RSS URL.
        
        Args:
            rss_url (str): RSS feed URL
            
        Returns:
            dict: Website data if found, None otherwise
        """
        from YSimulator.YServer.classes.models import Website
        
        session = Session(self.engine)
        try:
            website = session.query(Website).filter(Website.rss == rss_url).first()
            
            if website:
                return {
                    "id": website.id,
                    "name": website.name,
                    "rss": website.rss,
                    "category": website.category,
                    "language": website.language
                }
            return None
            
        except Exception as e:
            self.logger.error(
                f"Error getting website by RSS: {e}",
                extra={"extra_data": {"error": str(e), "rss_url": rss_url}}
            )
            return None
        finally:
            session.close()
