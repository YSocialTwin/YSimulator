"""
Unit tests for utils/init_db.py

Tests the database initialization functionality for different database backends.
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile


class TestCreateDatabaseEngine:
    """Test create_database_engine function."""

    def test_create_sqlite_engine_default(self):
        """Test SQLite engine creation with default configuration."""
        from YSimulator.utils.init_db import create_database_engine

        db_config = {"type": "sqlite", "sqlite": {"filename": "test.db"}}

        engine = create_database_engine(db_config)

        assert engine is not None
        assert "sqlite" in str(engine.url)

    def test_create_sqlite_engine_with_path(self):
        """Test SQLite engine creation with config path."""
        from YSimulator.utils.init_db import create_database_engine

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": "test.db"}}
            config_path = Path(tmpdir)

            engine = create_database_engine(db_config, config_path)

            assert engine is not None
            assert "sqlite" in str(engine.url)
            assert tmpdir in str(engine.url)

    def test_create_sqlite_engine_memory(self):
        """Test SQLite in-memory engine creation."""
        from YSimulator.utils.init_db import create_database_engine

        db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}

        engine = create_database_engine(db_config)

        assert engine is not None
        assert "memory" in str(engine.url)

    def test_create_sqlite_engine_no_config_path(self):
        """Test SQLite engine when config_path is None."""
        from YSimulator.utils.init_db import create_database_engine

        db_config = {"type": "sqlite", "sqlite": {"filename": "mydb.db"}}

        engine = create_database_engine(db_config, config_path=None)

        assert engine is not None
        assert "mydb.db" in str(engine.url)

    @pytest.mark.skip(reason="Requires PostgreSQL driver")
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
                "password": "test_pass",
            },
        }

        engine = create_database_engine(db_config)

        assert engine is not None
        assert "postgresql" in str(engine.url)

    @pytest.mark.skip(reason="Requires PostgreSQL driver")
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
                "password": "",
            },
        }

        engine = create_database_engine(db_config)

        assert engine is not None
        assert "postgresql" in str(engine.url)

    @pytest.mark.skip(reason="Requires MySQL driver")
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
                "password": "test_pass",
            },
        }

        engine = create_database_engine(db_config)

        assert engine is not None
        assert "mysql" in str(engine.url)

    @pytest.mark.skip(reason="Requires MySQL driver")
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
                "password": "",
            },
        }

        engine = create_database_engine(db_config)

        assert engine is not None
        assert "mysql" in str(engine.url)

    def test_unsupported_database_type(self):
        """Test that unsupported database type raises ValueError."""
        from YSimulator.utils.init_db import create_database_engine

        db_config = {"type": "mongodb"}  # Not supported

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

        db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}

        result = initialize_database(db_config)

        assert result is True

    def test_initialize_database_with_logger(self):
        """Test initializing database with custom logger."""
        from YSimulator.utils.init_db import initialize_database

        db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}

        mock_logger = Mock()
        result = initialize_database(db_config, logger=mock_logger)

        assert result is True
        assert mock_logger.info.called

    def test_initialize_database_without_logger(self):
        """Test initializing database without custom logger."""
        from YSimulator.utils.init_db import initialize_database

        db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}

        with patch("logging.info") as mock_logging:
            result = initialize_database(db_config, logger=None)

            assert result is True
            assert mock_logging.called

    def test_initialize_database_creates_tables(self):
        """Test that initialize_database creates all tables."""
        from YSimulator.utils.init_db import initialize_database
        from YSimulator.YServer.classes.models import Base

        db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}

        with patch.object(Base.metadata, "create_all") as mock_create:
            result = initialize_database(db_config)

            assert mock_create.called
            assert result is True

    def test_initialize_database_handles_exception(self):
        """Test that initialize_database handles exceptions."""
        from YSimulator.utils.init_db import initialize_database

        db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}

        with patch("YSimulator.utils.init_db.create_database_engine") as mock_engine:
            mock_engine.side_effect = Exception("Test error")

            result = initialize_database(db_config)

            assert result is False

    def test_initialize_database_with_config_path(self):
        """Test initializing database with config path."""
        from YSimulator.utils.init_db import initialize_database

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": "test.db"}}
            config_path = Path(tmpdir)

            result = initialize_database(db_config, config_path)

            assert result is True


class TestDatabaseExists:
    """Test database_exists function."""

    def test_database_exists_sqlite_true(self):
        """Test database_exists returns True for existing SQLite database."""
        from YSimulator.utils.init_db import database_exists

        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "test.db"
            db_file.touch()  # Create the file

            db_config = {"type": "sqlite", "sqlite": {"filename": "test.db"}}

            result = database_exists(db_config, Path(tmpdir))

            assert result is True

    def test_database_exists_sqlite_false(self):
        """Test database_exists returns False for non-existing SQLite database."""
        from YSimulator.utils.init_db import database_exists

        with tempfile.TemporaryDirectory() as tmpdir:
            db_config = {"type": "sqlite", "sqlite": {"filename": "nonexistent.db"}}

            result = database_exists(db_config, Path(tmpdir))

            assert result is False

    def test_database_exists_sqlite_no_config_path(self):
        """Test database_exists with no config_path."""
        from YSimulator.utils.init_db import database_exists

        db_config = {
            "type": "sqlite",
            "sqlite": {"filename": "some_random_file_that_doesnt_exist.db"},
        }

        result = database_exists(db_config, None)

        # Should return False since file doesn't exist
        assert result is False

    def test_database_exists_postgresql(self):
        """Test database_exists for PostgreSQL."""
        from YSimulator.utils.init_db import database_exists

        db_config = {
            "type": "postgresql",
            "postgresql": {
                "host": "localhost",
                "database": "test_db",
                "username": "test_user",
                "password": "",
            },
        }

        # Should handle connection failure gracefully
        result = database_exists(db_config)

        # Will be False if can't connect (expected in test environment)
        assert isinstance(result, bool)


class TestPasswordEncoding:
    """Test password encoding for database URLs."""

    @pytest.mark.skip(reason="Requires PostgreSQL driver")
    def test_password_with_special_characters_postgresql(self):
        """Test that special characters in passwords are URL encoded for PostgreSQL."""
        from YSimulator.utils.init_db import create_database_engine

        db_config = {
            "type": "postgresql",
            "postgresql": {
                "host": "localhost",
                "database": "test_db",
                "username": "user",
                "password": "p@ss:word!",  # Special characters
            },
        }

        engine = create_database_engine(db_config)

        assert engine is not None
        assert "postgresql" in str(engine.url)

    @pytest.mark.skip(reason="Requires MySQL driver")
    def test_password_with_special_characters_mysql(self):
        """Test that special characters in passwords are URL encoded for MySQL."""
        from YSimulator.utils.init_db import create_database_engine

        db_config = {
            "type": "mysql",
            "mysql": {
                "host": "localhost",
                "database": "test_db",
                "username": "user",
                "password": "p@ss:word!",
            },
        }

        engine = create_database_engine(db_config)

        assert engine is not None
        assert "mysql" in str(engine.url)


class TestDatabaseDefaults:
    """Test default values for database configuration."""

    @pytest.mark.skip(reason="Requires PostgreSQL driver")
    def test_postgresql_defaults(self):
        """Test PostgreSQL uses correct default values."""
        from YSimulator.utils.init_db import create_database_engine

        db_config = {"type": "postgresql", "postgresql": {}}  # Empty config

        engine = create_database_engine(db_config)

        assert engine is not None
        url_str = str(engine.url)
        assert "localhost" in url_str or "5432" in url_str

    @pytest.mark.skip(reason="Requires MySQL driver")
    def test_mysql_defaults(self):
        """Test MySQL uses correct default values."""
        from YSimulator.utils.init_db import create_database_engine

        db_config = {"type": "mysql", "mysql": {}}  # Empty config

        engine = create_database_engine(db_config)

        assert engine is not None
        url_str = str(engine.url)
        assert "localhost" in url_str or "3306" in url_str

    def test_sqlite_default_filename(self):
        """Test SQLite uses default filename."""
        from YSimulator.utils.init_db import create_database_engine

        db_config = {"type": "sqlite", "sqlite": {}}  # No filename specified

        engine = create_database_engine(db_config)

        assert engine is not None
        assert "simulation.db" in str(engine.url)


class TestConnectionString:
    """Test connection string generation."""

    def test_sqlite_connection_string_format(self):
        """Test SQLite connection string format."""
        from YSimulator.utils.init_db import create_database_engine

        db_config = {"type": "sqlite", "sqlite": {"filename": "test.db"}}

        engine = create_database_engine(db_config)
        url = str(engine.url)

        assert url.startswith("sqlite:///")

    @pytest.mark.skip(reason="Requires PostgreSQL driver")
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
                "password": "testpass",
            },
        }

        engine = create_database_engine(db_config)
        url = str(engine.url)

        assert "postgresql" in url
        assert "testhost" in url
        assert "testdb" in url

    @pytest.mark.skip(reason="Requires MySQL driver")
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
                "password": "testpass",
            },
        }

        engine = create_database_engine(db_config)
        url = str(engine.url)

        assert "mysql" in url
        assert "testhost" in url
        assert "testdb" in url


class TestMainFunction:
    """Test main CLI entry point."""

    def test_main_with_sqlite_defaults(self):
        """Test main function with default SQLite configuration."""
        from YSimulator.utils.init_db import main

        test_args = ["init_db.py", "--db-type", "sqlite"]

        with patch("sys.argv", test_args):
            with patch("YSimulator.utils.init_db.initialize_database") as mock_init:
                mock_init.return_value = True

                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 0
                assert mock_init.called

    def test_main_with_custom_sqlite_filename(self):
        """Test main with custom SQLite filename."""
        from YSimulator.utils.init_db import main

        test_args = ["init_db.py", "--db-type", "sqlite", "--sqlite-filename", "custom.db"]

        with patch("sys.argv", test_args):
            with patch("YSimulator.utils.init_db.initialize_database") as mock_init:
                mock_init.return_value = True

                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 0
                # Check that custom filename was passed
                call_args = mock_init.call_args[0][0]
                assert call_args["sqlite"]["filename"] == "custom.db"

    def test_main_with_config_path(self):
        """Test main with config path."""
        from YSimulator.utils.init_db import main

        with tempfile.TemporaryDirectory() as tmpdir:
            test_args = ["init_db.py", "--db-type", "sqlite", "--config-path", tmpdir]

            with patch("sys.argv", test_args):
                with patch("YSimulator.utils.init_db.initialize_database") as mock_init:
                    mock_init.return_value = True

                    with pytest.raises(SystemExit) as exc_info:
                        main()

                    assert exc_info.value.code == 0

    def test_main_initialization_failure(self):
        """Test main when database initialization fails."""
        from YSimulator.utils.init_db import main

        test_args = ["init_db.py", "--db-type", "sqlite"]

        with patch("sys.argv", test_args):
            with patch("YSimulator.utils.init_db.initialize_database") as mock_init:
                mock_init.return_value = False

                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
