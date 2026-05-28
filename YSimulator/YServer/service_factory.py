"""
Service Factory for YSimulator.

This module provides factory functions to create service instances
with appropriate repository implementations based on configuration.
"""

import logging
from typing import Any, Dict, Optional

try:
    from sqlalchemy import create_engine
    from sqlalchemy.engine import Engine

    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    create_engine = None
    Engine = None

try:
    from YSimulator.YServer.repositories.sql_repository import (
        SQLArticleRepository,
        SQLFollowRepository,
        SQLImageRepository,
        SQLInterestRepository,
        SQLPostRepository,
        SQLRecommendationRepository,
        SQLUserRepository,
    )
    from YSimulator.YServer.services.article_service import ArticleService
    from YSimulator.YServer.services.content_service import ContentService
    from YSimulator.YServer.services.follow_service import FollowService
    from YSimulator.YServer.services.image_service import ImageService
    from YSimulator.YServer.services.interest_service import InterestService
    from YSimulator.YServer.services.memory_service import MemoryService
    from YSimulator.YServer.services.mention_service import MentionService
    from YSimulator.YServer.services.metadata_service import MetadataService
    from YSimulator.YServer.services.post_service import PostService
    from YSimulator.YServer.services.simulation_service import SimulationService
    from YSimulator.YServer.services.user_service import UserService

    SERVICES_AVAILABLE = True
except ImportError as e:
    SERVICES_AVAILABLE = False
    import_error = e


def create_database_engine(
    db_config: Dict[str, Any], config_path: str = ".", logger: Optional[logging.Logger] = None
):
    """
    Create SQLAlchemy engine from database configuration and initialize database tables.

    Args:
        db_config: Database configuration dict with:
            - type: "sqlite", "postgresql", or "mysql"
            - Additional connection parameters
        config_path: Path to configuration directory (for SQLite database file)
        logger: Optional logger instance

    Returns:
        SQLAlchemy Engine instance with tables created
    """
    from pathlib import Path

    if not SQLALCHEMY_AVAILABLE:
        raise ImportError(
            "SQLAlchemy is not installed. Please install it with: pip install sqlalchemy>=2.0.0"
        )

    if logger is None:
        logger = logging.getLogger(__name__)

    db_type = db_config.get("type", "sqlite")

    if db_type == "sqlite":
        # Support both old and new config formats
        # Old format: {"type": "sqlite", "sqlite": {"filename": "simulation.db"}}
        # New format: {"type": "sqlite", "path": "simulation.db"}
        sqlite_config = db_config.get("sqlite", {})
        filename = sqlite_config.get("filename") or db_config.get("path", "simulation.db")

        # Create database file in config directory (same as old middleware)
        db_path = Path(config_path) / filename
        connection_string = f"sqlite:///{db_path}"
    elif db_type == "postgresql":
        host = db_config.get("host", "localhost")
        port = db_config.get("port", 5432)
        database = db_config.get("database", "ysimulator")
        user = db_config.get("user", "postgres")
        password = db_config.get("password", "")
        connection_string = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    elif db_type == "mysql":
        host = db_config.get("host", "localhost")
        port = db_config.get("port", 3306)
        database = db_config.get("database", "ysimulator")
        user = db_config.get("user", "root")
        password = db_config.get("password", "")
        connection_string = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
    else:
        raise ValueError(f"Unsupported database type: {db_type}")

    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }
    if db_type == "sqlite":
        engine_kwargs["connect_args"] = {"timeout": 30}

    # Create engine with connection pooling
    engine = create_engine(connection_string, **engine_kwargs)

    # Create all tables if they don't exist
    try:
        from YSimulator.YServer.classes.models import Base
        from YSimulator.YServer.schema_migrations import ensure_moderation_schema

        Base.metadata.create_all(engine)
        ensure_moderation_schema(engine)
        logger.info(f"Database tables created/verified for {db_type}")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise

    return engine


def create_all_services(
    db_config: Dict[str, Any],
    config_path: str = ".",
    logger: Optional[logging.Logger] = None,
):
    """
    Create all service instances with repository dependencies.

    Args:
        db_config: Database configuration dict
        config_path: Path to configuration directory (for SQLite database file)
        logger: Optional logger instance

    Returns:
        Tuple of (UserService, PostService, FollowService, InterestService,
        ArticleService, ImageService, ContentService, SimulationService,
        MetadataService, MentionService)
    """
    if not SERVICES_AVAILABLE:
        raise ImportError(
            f"Required dependencies are not installed. "
            f"Please install with: pip install -r requirements.txt\n"
            f"Error: {import_error if 'import_error' in globals() else 'Unknown import error'}"
        )

    if logger is None:
        logger = logging.getLogger(__name__)

    # Create database engine and initialize tables
    engine = create_database_engine(db_config, config_path, logger)

    # Create all repositories
    user_repo = SQLUserRepository(engine, logger)
    post_repo = SQLPostRepository(engine, logger)
    follow_repo = SQLFollowRepository(engine, logger)
    interest_repo = SQLInterestRepository(engine, logger)
    article_repo = SQLArticleRepository(engine, logger)
    image_repo = SQLImageRepository(engine, logger)
    recommendation_repo = SQLRecommendationRepository(engine, logger)

    # Create specialized services
    user_service = UserService(
        user_repository=user_repo,
        interest_repository=interest_repo,
        logger=logger,
    )

    post_service = PostService(
        post_repository=post_repo,
        interest_repository=interest_repo,
        logger=logger,
    )

    follow_service = FollowService(
        follow_repository=follow_repo,
        logger=logger,
    )

    interest_service = InterestService(
        interest_repository=interest_repo,
        logger=logger,
    )

    # Create new specialized services for articles and images
    article_service = ArticleService(
        article_repository=article_repo,
        interest_repository=interest_repo,
        logger=logger,
    )

    image_service = ImageService(
        image_repository=image_repo,
        logger=logger,
    )

    # Create ContentService that uses ArticleService and ImageService
    content_service = ContentService(
        article_repository=article_repo,
        image_repository=image_repo,
        article_service=article_service,
        image_service=image_service,
        logger=logger,
    )

    simulation_service = SimulationService(
        recommendation_repository=recommendation_repo,
        logger=logger,
    )

    metadata_service = MetadataService(
        post_repository=post_repo,
        logger=logger,
    )

    mention_service = MentionService(
        post_repository=post_repo,
        engine=engine,
        logger=logger,
    )

    memory_service = MemoryService(
        engine=engine,
        logger=logger,
        config_path=config_path,
    )

    return (
        user_service,
        post_service,
        follow_service,
        interest_service,
        article_service,
        image_service,
        content_service,
        simulation_service,
        metadata_service,
        mention_service,
        memory_service,
    )


def create_services(
    db_config: Dict[str, Any],
    config_path: str = ".",
    logger: Optional[logging.Logger] = None,
):
    """
    Create basic service instances with repository dependencies.

    DEPRECATED: Use create_all_services() instead.

    Args:
        db_config: Database configuration dict
        config_path: Path to configuration directory (for SQLite database file)
        logger: Optional logger instance

    Returns:
        Tuple of (UserService, PostService)
    """
    # This function is kept for backward compatibility
    all_services = create_all_services(db_config, config_path, logger)
    return all_services[0], all_services[1]  # Return only UserService and PostService
