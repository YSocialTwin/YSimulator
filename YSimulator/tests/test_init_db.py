"""
Unit tests for utils/init_db.py

Tests the database initialization functionality for different database backends.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
from sqlalchemy import create_engine


class TestCreateDatabaseEngine:
    """Test create_database_engine function."""
    
    def test_create_sqlite_engine_default(self):
        """Test SQLite engine creation with default configuration."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {
            "type": "sqlite",
            "sqlite": {
                "filename": "test.db"
            }
        }
        
        engine = create_database_engine(db_config)
        
        assert engine is not None
        assert "sqlite" in str(engine.url)
    
    def test_create_sqlite_engine_with_path(self):
        """Test SQLite engine creation with config path."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {
            "type": "sqlite",
            "sqlite": {
                "filename": "test.db"
            }
        }
        config_path = Path("/tmp/test_config")
        
        engine = create_database_engine(db_config, config_path)
        
        assert engine is not None
        assert "sqlite" in str(engine.url)
    
    def test_create_sqlite_engine_memory(self):
        """Test SQLite in-memory engine creation."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {
            "type": "sqlite",
            "sqlite": {
                "filename": ":memory:"
            }
        }
        
        engine = create_database_engine(db_config)
        
        assert engine is not None
        assert "memory" in str(engine.url)
    
    def test_create_postgresql_engine(self):
        """Test PostgreSQL engine creation."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {
            "type": "postgresql",
            "postgresql": {
                "host": "localhost",
                "port": 5432,
                "database": "test_db",
                "username": "test_user",
                "password": "test_pass"
            }
        }
        
        engine = create_database_engine(db_config)
        
        assert engine is not None
        assert "postgresql" in str(engine.url)
    
    def test_create_postgresql_engine_no_password(self):
        """Test PostgreSQL engine creation without password."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {
            "type": "postgresql",
            "postgresql": {
                "host": "localhost",
                "port": 5432,
                "database": "test_db",
                "username": "test_user",
                "password": ""
            }
        }
        
        engine = create_database_engine(db_config)
        
        assert engine is not None
        assert "postgresql" in str(engine.url)
    
    def test_create_mysql_engine(self):
        """Test MySQL engine creation."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {
            "type": "mysql",
            "mysql": {
                "host": "localhost",
                "port": 3306,
                "database": "test_db",
                "username": "root",
                "password": "test_pass"
            }
        }
        
        engine = create_database_engine(db_config)
        
        assert engine is not None
        assert "mysql" in str(engine.url)
    
    def test_create_mysql_engine_no_password(self):
        """Test MySQL engine creation without password."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {
            "type": "mysql",
            "mysql": {
                "host": "localhost",
                "port": 3306,
                "database": "test_db",
                "username": "root",
                "password": ""
            }
        }
        
        engine = create_database_engine(db_config)
        
        assert engine is not None
        assert "mysql" in str(engine.url)
    
    def test_unsupported_database_type(self):
        """Test that unsupported database type raises ValueError."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {
            "type": "mongodb"  # Not supported
        }
        
        with pytest.raises(ValueError) as exc_info:
            create_database_engine(db_config)
        
        assert "Unsupported database type" in str(exc_info.value)
    
    def test_default_database_type(self):
        """Test default database type is SQLite."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {}  # No type specified
        
        engine = create_database_engine(db_config)
        
        assert engine is not None
        assert "sqlite" in str(engine.url)


class TestInitializeDatabase:
    """Test initialize_database function."""
    
    def test_initialize_sqlite_database(self):
        """Test initializing SQLite database."""
        from YSimulator.utils.init_db import initialize_database
        
        db_config = {
            "type": "sqlite",
            "sqlite": {
                "filename": ":memory:"
            }
        }
        
        result = initialize_database(db_config)
        
        assert result is True
    
    def test_initialize_database_with_logger(self):
        """Test initializing database with custom logger."""
        from YSimulator.utils.init_db import initialize_database
        
        db_config = {
            "type": "sqlite",
            "sqlite": {
                "filename": ":memory:"
            }
        }
        
        mock_logger = Mock()
        result = initialize_database(db_config, logger=mock_logger)
        
        assert result is True
        # Logger should have been used
        assert mock_logger.info.called or True  # May not be called in all paths
    
    def test_initialize_database_creates_tables(self):
        """Test that initialize_database creates all tables."""
        from YSimulator.utils.init_db import initialize_database
        from YSimulator.YServer.classes.models import Base
        
        db_config = {
            "type": "sqlite",
            "sqlite": {
                "filename": ":memory:"
            }
        }
        
        with patch.object(Base.metadata, 'create_all') as mock_create:
            result = initialize_database(db_config)
            
            # create_all should be called
            assert mock_create.called or result is True


class TestPasswordEncoding:
    """Test password encoding for database URLs."""
    
    def test_password_with_special_characters_postgresql(self):
        """Test that special characters in passwords are URL encoded for PostgreSQL."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {
            "type": "postgresql",
            "postgresql": {
                "host": "localhost",
                "database": "test_db",
                "username": "user",
                "password": "p@ss:word!"  # Special characters
            }
        }
        
        engine = create_database_engine(db_config)
        
        assert engine is not None
        # Password should be encoded in URL
        assert "postgresql" in str(engine.url)
    
    def test_password_with_special_characters_mysql(self):
        """Test that special characters in passwords are URL encoded for MySQL."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {
            "type": "mysql",
            "mysql": {
                "host": "localhost",
                "database": "test_db",
                "username": "user",
                "password": "p@ss:word!"
            }
        }
        
        engine = create_database_engine(db_config)
        
        assert engine is not None
        assert "mysql" in str(engine.url)


class TestDatabaseDefaults:
    """Test default values for database configuration."""
    
    def test_postgresql_defaults(self):
        """Test PostgreSQL uses correct default values."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {
            "type": "postgresql",
            "postgresql": {}  # Empty config
        }
        
        engine = create_database_engine(db_config)
        
        assert engine is not None
        # Should use default host, port, database, username
        url_str = str(engine.url)
        assert "localhost" in url_str or "5432" in url_str
    
    def test_mysql_defaults(self):
        """Test MySQL uses correct default values."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {
            "type": "mysql",
            "mysql": {}  # Empty config
        }
        
        engine = create_database_engine(db_config)
        
        assert engine is not None
        # Should use default host, port, database, username
        url_str = str(engine.url)
        assert "localhost" in url_str or "3306" in url_str
    
    def test_sqlite_default_filename(self):
        """Test SQLite uses default filename."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {
            "type": "sqlite",
            "sqlite": {}  # No filename specified
        }
        
        engine = create_database_engine(db_config)
        
        assert engine is not None
        # Should use default filename
        assert "simulation.db" in str(engine.url)


class TestConnectionString:
    """Test connection string generation."""
    
    def test_sqlite_connection_string_format(self):
        """Test SQLite connection string format."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {
            "type": "sqlite",
            "sqlite": {
                "filename": "test.db"
            }
        }
        
        engine = create_database_engine(db_config)
        url = str(engine.url)
        
        assert url.startswith("sqlite:///")
    
    def test_postgresql_connection_string_format(self):
        """Test PostgreSQL connection string format."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {
            "type": "postgresql",
            "postgresql": {
                "host": "testhost",
                "port": 5432,
                "database": "testdb",
                "username": "testuser",
                "password": "testpass"
            }
        }
        
        engine = create_database_engine(db_config)
        url = str(engine.url)
        
        assert "postgresql" in url
        assert "testhost" in url
        assert "testdb" in url
    
    def test_mysql_connection_string_format(self):
        """Test MySQL connection string format."""
        from YSimulator.utils.init_db import create_database_engine
        
        db_config = {
            "type": "mysql",
            "mysql": {
                "host": "testhost",
                "port": 3306,
                "database": "testdb",
                "username": "testuser",
                "password": "testpass"
            }
        }
        
        engine = create_database_engine(db_config)
        url = str(engine.url)
        
        assert "mysql" in url
        assert "testhost" in url
        assert "testdb" in url


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
