"""
Pytest configuration and fixtures for YSimulator tests.

This module provides:
- Database isolation between tests
- NLTK data downloads
- Common test fixtures
- Test database setup/teardown
- Ray initialization for distributed tests
"""

import os
import tempfile
from pathlib import Path
from typing import Generator

import nltk
import pytest
import ray
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Initialize Ray BEFORE any other imports that might use Ray decorators
# This ensures @ray.remote decorators work correctly
if not ray.is_initialized():
    ray.init(ignore_reinit_error=True, num_cpus=1)

# Download required NLTK data
try:
    nltk.data.find("sentiment/vader_lexicon")
except LookupError:
    nltk.download("vader_lexicon", quiet=True)


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Provide a temporary directory for test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(scope="function")
def isolated_db() -> Generator[str, None, None]:
    """
    Provide an isolated SQLite database for each test.
    
    This fixture creates a new temporary database for each test function,
    ensuring complete isolation between tests.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmpfile:
        db_path = tmpfile.name
    
    db_url = f"sqlite:///{db_path}"
    
    yield db_url
    
    # Cleanup
    try:
        if os.path.exists(db_path):
            os.unlink(db_path)
    except (OSError, PermissionError) as e:
        # Best effort cleanup - log but don't fail test
        import logging
        logging.getLogger(__name__).debug(f"Cleanup failed for {db_path}: {e}")


@pytest.fixture(scope="function")
def db_session(isolated_db: str) -> Generator[Session, None, None]:
    """
    Provide a SQLAlchemy session with an isolated database.
    
    This fixture creates a new session for each test, with automatic
    rollback and cleanup after the test completes.
    """
    engine = create_engine(isolated_db)
    SessionLocal = sessionmaker(bind=engine)
    
    # Import models to ensure tables are created
    try:
        from YSimulator.YServer.classes.models import Base
        Base.metadata.create_all(engine)
    except ImportError:
        pass  # Models not available in all test contexts
    
    session = SessionLocal()
    
    yield session
    
    session.close()
    engine.dispose()


@pytest.fixture(scope="function")
def sample_agent_data() -> dict:
    """Provide sample agent data for testing."""
    return {
        "id": "test-agent-123",
        "username": "test_agent",
        "email": "test@example.com",
        "password": "test_password",
        "user_type": "agent",
        "leaning": "neutral",
        "round_actions": 3,
        "is_page": False,
        "daily_activity_level": 1,
        "archetype": "validator",
    }


@pytest.fixture(scope="function")
def sample_post_data() -> dict:
    """Provide sample post data for testing."""
    return {
        "id": "test-post-123",
        "author_id": "test-agent-123",
        "content": "This is a test post #testing",
        "day": 1,
        "hour": 12,
        "thread_id": "thread-123",
    }


@pytest.fixture(autouse=True)
def reset_singletons():
    """
    Reset singleton instances between tests.
    
    This ensures that singleton objects don't carry state between tests.
    """
    yield
    # Add any singleton reset logic here if needed


@pytest.fixture(scope="session")
def nltk_data_available() -> bool:
    """Check if required NLTK data is available."""
    try:
        nltk.data.find("sentiment/vader_lexicon")
        return True
    except LookupError:
        return False
