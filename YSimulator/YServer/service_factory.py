"""
Service Factory for YSimulator.

This module provides factory functions to create service instances
with appropriate repository implementations based on configuration.
"""

import logging
from typing import Dict, Any, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from YSimulator.YServer.repositories.sql_repository import (
    SQLUserRepository,
    SQLPostRepository,
    SQLFollowRepository,
    SQLInterestRepository,
)
from YSimulator.YServer.services.user_service import UserService
from YSimulator.YServer.services.post_service import PostService


def create_database_engine(db_config: Dict[str, Any]) -> Engine:
    """
    Create SQLAlchemy engine from database configuration.
    
    Args:
        db_config: Database configuration dict with:
            - type: "sqlite", "postgresql", or "mysql"
            - Additional connection parameters
    
    Returns:
        SQLAlchemy Engine instance
    """
    db_type = db_config.get("type", "sqlite")
    
    if db_type == "sqlite":
        db_path = db_config.get("path", "simulation.db")
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
    
    # Create engine with connection pooling
    engine = create_engine(
        connection_string,
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,  # Recycle connections after 1 hour
    )
    
    return engine


def create_services(
    db_config: Dict[str, Any],
    logger: Optional[logging.Logger] = None,
) -> Tuple[UserService, PostService]:
    """
    Create service instances with repository dependencies.
    
    Args:
        db_config: Database configuration dict
        logger: Optional logger instance
    
    Returns:
        Tuple of (UserService, PostService)
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    # Create database engine
    engine = create_database_engine(db_config)
    
    # Create repositories
    user_repo = SQLUserRepository(engine, logger)
    post_repo = SQLPostRepository(engine, logger)
    follow_repo = SQLFollowRepository(engine, logger)
    interest_repo = SQLInterestRepository(engine, logger)
    
    # Create services
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
    
    return user_service, post_service
